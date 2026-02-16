"""
Task Base — Classe de base robuste pour toutes les tâches Celery.

Fournit :
  - Structured logging avec request_id et task_id
  - Classification d'erreurs (retryable vs fatales)
  - Exponential backoff avec jitter
  - Métriques de timing
  - Gestion propre des SoftTimeLimitExceeded
  - Hooks on_success / on_failure / on_retry
  - Circuit breaker pattern (optionnel)

Toutes les tâches AgriConnect DOIVENT hériter de AgriTask
via @celery_app.task(base=AgriTask).
"""

import logging
import random
import time
import uuid
from typing import Any, Dict, Optional

from celery import Task
from celery.exceptions import (
    MaxRetriesExceededError,
    Reject,
    SoftTimeLimitExceeded,
)

logger = logging.getLogger("AgriConnect.tasks")


# ── Exceptions classifiées ──────────────────────────────────

class RetryableError(Exception):
    """Erreur transitoire — la tâche doit être re-tentée."""
    pass


class FatalTaskError(Exception):
    """Erreur permanente — ne PAS retenter, log + dead-letter."""
    pass


class RateLimitHit(RetryableError):
    """Le provider externe a renvoyé un 429 — backoff long."""
    pass


class ExternalServiceDown(RetryableError):
    """Service externe indisponible (5xx, timeout réseau)."""
    pass


# ── Résultats structurés ────────────────────────────────────

def success_result(data: Dict[str, Any], task_name: str = "") -> Dict[str, Any]:
    """Format de résultat standardisé pour les succès."""
    return {
        "status": "success",
        "task": task_name,
        "timestamp": time.time(),
        **data,
    }


def error_result(
    error: str,
    task_name: str = "",
    retryable: bool = False,
    details: Optional[Dict] = None,
) -> Dict[str, Any]:
    """Format de résultat standardisé pour les erreurs terminales."""
    result = {
        "status": "error",
        "task": task_name,
        "error": error,
        "retryable": retryable,
        "timestamp": time.time(),
    }
    if details:
        result["details"] = details
    return result


# ── Task Base Class ─────────────────────────────────────────

class AgriTask(Task):
    """
    Classe de base pour toutes les tâches AgriConnect.

    Usage:
        @celery_app.task(base=AgriTask, bind=True, ...)
        def my_task(self, ...):
            ...

    Fonctionnalités :
      - request_id injecté automatiquement (pour tracing end-to-end)
      - Exponential backoff avec jitter (au lieu d'un delay fixe)
      - Gestion SoftTimeLimitExceeded → cleanup + fail propre
      - Classification automatique des erreurs
      - Logging structuré cohérent
    """

    # ── Defaults (overridables par tâche) ──
    abstract = True
    autoretry_for = (RetryableError, ExternalServiceDown, RateLimitHit)
    max_retries = 3
    default_retry_delay = 10

    # Exponential backoff config
    retry_backoff = True
    retry_backoff_max = 300  # 5 min max entre retries
    retry_jitter = True      # ajoute du random pour éviter les thundering herds

    # Tracking
    track_started = True
    acks_late = True

    def before_start(self, task_id: str, args: tuple, kwargs: dict):
        """Hook appelé AVANT l'exécution. Injecte le request_id."""
        self._start_time = time.monotonic()
        self._request_id = kwargs.pop("request_id", None) or str(uuid.uuid4())[:8]
        self._task_logger = logging.getLogger(f"AgriConnect.tasks.{self.name}")
        self._task_logger.info(
            "[%s] ▶ START task=%s args=%s",
            self._request_id, self.name, self._format_args(args, kwargs),
        )

    def on_success(self, retval: Any, task_id: str, args: tuple, kwargs: dict):
        """Hook appelé après un succès."""
        elapsed = time.monotonic() - getattr(self, "_start_time", time.monotonic())
        req_id = getattr(self, "_request_id", "?")
        self._get_logger().info(
            "[%s] ✅ SUCCESS task=%s elapsed=%.2fs",
            req_id, self.name, elapsed,
        )

    def on_failure(self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo):
        """Hook appelé après un échec terminal (tous retries épuisés)."""
        elapsed = time.monotonic() - getattr(self, "_start_time", time.monotonic())
        req_id = getattr(self, "_request_id", "?")
        self._get_logger().error(
            "[%s] ❌ FAILED task=%s elapsed=%.2fs error=%s",
            req_id, self.name, elapsed, exc,
            exc_info=True,
        )

    def on_retry(self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo):
        """Hook appelé à chaque retry."""
        attempt = self.request.retries + 1
        req_id = getattr(self, "_request_id", "?")
        self._get_logger().warning(
            "[%s] 🔄 RETRY task=%s attempt=%d/%d error=%s",
            req_id, self.name, attempt, self.max_retries, exc,
        )

    def retry_with_backoff(
        self,
        exc: Exception,
        base_delay: float = 5.0,
        max_delay: float = 300.0,
        jitter: bool = True,
    ):
        """
        Retry avec exponential backoff + jitter.

        Formule : delay = min(base_delay * 2^attempt + jitter, max_delay)
        """
        attempt = self.request.retries
        delay = min(base_delay * (2 ** attempt), max_delay)
        if jitter:
            delay += random.uniform(0, delay * 0.3)

        req_id = getattr(self, "_request_id", "?")
        self._get_logger().info(
            "[%s] ⏳ Scheduling retry in %.1fs (attempt %d/%d)",
            req_id, delay, attempt + 1, self.max_retries,
        )

        try:
            raise self.retry(exc=exc, countdown=delay)
        except MaxRetriesExceededError:
            self._get_logger().error(
                "[%s] 💀 Max retries exceeded for task=%s",
                req_id, self.name,
            )
            raise

    def handle_timeout(self, partial_result: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Appelé manuellement dans un except SoftTimeLimitExceeded.
        Retourne un résultat d'erreur propre au lieu de crasher.
        """
        req_id = getattr(self, "_request_id", "?")
        self._get_logger().error(
            "[%s] ⏰ TIMEOUT task=%s (soft limit exceeded)",
            req_id, self.name,
        )
        result = error_result(
            error="Task timed out",
            task_name=self.name,
            retryable=False,
            details=partial_result,
        )
        return result

    @staticmethod
    def classify_error(exc: Exception) -> str:
        """
        Classifie une erreur pour décider du comportement retry.

        Returns:
            "retry"  → erreur transitoire, réessayer
            "fatal"  → erreur permanente, ne pas réessayer
            "rate_limit" → 429, backoff long
        """
        exc_str = str(exc).lower()
        exc_type = type(exc).__name__

        # ── Fatales : ne pas retenter ──
        fatal_patterns = [
            "invalid api key", "authentication", "unauthorized",
            "forbidden", "not found", "invalid", "permission denied",
            "quota exceeded permanently",
        ]
        if any(p in exc_str for p in fatal_patterns):
            return "fatal"
        if isinstance(exc, (ValueError, TypeError, KeyError, FatalTaskError)):
            return "fatal"

        # ── Rate limits : backoff long ──
        rate_patterns = ["rate limit", "429", "too many requests", "throttl"]
        if any(p in exc_str for p in rate_patterns):
            return "rate_limit"
        if isinstance(exc, RateLimitHit):
            return "rate_limit"

        # ── Tout le reste : retryable ──
        return "retry"

    # ── Helpers privés ──

    def _get_logger(self) -> logging.Logger:
        return getattr(self, "_task_logger", logger)

    @staticmethod
    def _format_args(args: tuple, kwargs: dict, max_len: int = 100) -> str:
        """Formate les arguments pour le logging (tronqué)."""
        parts = []
        for a in args:
            s = repr(a)
            parts.append(s[:max_len] + "…" if len(s) > max_len else s)
        for k, v in kwargs.items():
            s = repr(v)
            parts.append(f"{k}={s[:max_len]}{'…' if len(s) > max_len else ''}")
        return ", ".join(parts) or "(none)"
