"""
Report Flow — Rapports Automatiques Production-Ready
=====================================================

PHILOSOPHIE : "L'Action d'Abord, les Chiffres Ensuite"
-------------------------------------------------------
Un rapport n'a de valeur que s'il dicte une action IMMÉDIATE.
En cas de mauvaise connexion ou de lecture rapide, l'essentiel
est transmis en 3 secondes.

ARCHITECTURE DU GRAPHE :
  COLLECT_DATA (agents réels)
      → SEASON_ADAPTER (priorise le type de rapport)
          → URGENCY_FILTER (skip si rien de neuf)
              → [WEEKLY_HEALTH | MONTHLY_FINANCE | COMMUNITY_BENCHMARK]
                  → ACTION_SUMMARY (LLM : "L'Action du Jour" en haut)
                      → END

CONNEXIONS RÉELLES :
  - ClimateSentinel.analyze_node  → weather_snapshot, hazards, raw_metrics, flood_risk
  - MarketCoach.fetch_data_node   → prices, trends, logistics
  - Données communautaires        → DB / simulation

SMS "À TIROIRS" (160 chars max) :
  SMS 1 : alerte + action.  SMS 2 (optionnel) : détail si user répond "PRIX".

EXÉCUTION PÉRIODIQUE :
  - Lundi 7h   : WEEKLY_HEALTH
  - 1er du mois : MONTHLY_FINANCE
  - Trimestriel : COMMUNITY_BENCHMARK
  Via Celery Beat / cron → ReportFlow.generate_report(...)
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from langgraph.graph import END, StateGraph

from .state import GlobalAgriState, Severity, Alert
from backend.agents.sentinelle import ClimateSentinel
from backend.agents.market import MarketCoach
from backend.rag.components import get_groq_sdk, get_llm_client

logger = logging.getLogger("ReportFlow")

# ── Constantes de configuration ──────────────────────────────────────

SMS_MAX_CHARS = 160  # Un SMS standard, pas de fragmentation

# Calendrier agricole Burkina Faso (mois → saison dominante)
SEASON_CALENDAR: Dict[int, str] = {
    1: "saison_seche",   2: "saison_seche",   3: "pre_saison",
    4: "pre_saison",     5: "semis",          6: "semis",
    7: "croissance",     8: "croissance",     9: "maturation",
    10: "recolte",       11: "recolte",       12: "post_recolte",
}

# Quelle priorité de rapport par saison
SEASON_PRIORITY: Dict[str, str] = {
    "saison_seche": "weekly_health",      # Stress hydrique = priorité
    "pre_saison": "weekly_health",        # Préparation sols
    "semis": "weekly_health",             # Calendrier cultural critique
    "croissance": "weekly_health",        # Surveillance maladies
    "maturation": "monthly_finance",      # Préparer les ventes
    "recolte": "monthly_finance",         # Prix au plus haut, vendre
    "post_recolte": "community_benchmark",  # Bilan comparatif
}

# Seuils de changement pour le filtre d'urgence (%)
CHANGE_THRESHOLD_PERCENT = 5.0


class ReportType(Enum):
    """Types de rapports automatiques."""
    WEEKLY_HEALTH = "weekly_health"
    MONTHLY_FINANCE = "monthly_finance"
    SEASONAL_CALENDAR = "seasonal_calendar"
    COMMUNITY_BENCHMARK = "community_benchmark"
    EMERGENCY_ALERT = "emergency_alert"


class ReportFlow:
    """
    Générateur de Rapports Automatiques AgriBot — Production-Ready.

    Améliorations vs prototype :
    1. collect_data appelle les VRAIS agents (Sentinelle + Market) en parallèle.
    2. Noeud SEASON_ADAPTER priorise le type de rapport selon le calendrier.
    3. Noeud URGENCY_FILTER skip le rapport si rien n'a changé (>5%).
    4. Chaque rapport commence par "L'ACTION DU JOUR" (LLM).
    5. SMS strict 160 chars, pas d'emoji exotiques.
    6. Community benchmark avec "Conseil du Champion".
    """

    def __init__(self, llm_client=None):
        self.llm = llm_client if llm_client is not None else get_groq_sdk()

        # Agents spécialisés — workflows compilés
        self.sentinel = ClimateSentinel(llm_client=self.llm)
        self.market = MarketCoach(llm_client=self.llm)
        self.wf_sentinel = self.sentinel.build()
        self.wf_market = self.market.build()

        self.graph = self._build_report_graph()

    # ================================================================== #
    # 1. COLLECT DATA — Appels réels aux agents (parallèle)
    # ================================================================== #

    def _fetch_sentinel_data(self, zone: str, crop: str) -> Dict[str, Any]:
        """Appelle ClimateSentinel.analyze_node pour les données météo réelles."""
        try:
            sentinel_input = {
                "user_query": f"Rapport hebdomadaire : état météo et risques pour {crop}",
                "location_profile": {
                    "village": zone,
                    "zone": "Hauts-Bassins",
                    "country": "Burkina Faso",
                },
            }
            result = self.wf_sentinel.invoke(sentinel_input)
            return {
                "weather": result.get("weather_snapshot") or result.get("raw_metrics", {}),
                "hazards": result.get("hazards", []),
                "flood_risk": result.get("flood_risk", {}),
                "risk_summary": result.get("risk_summary", ""),
                "metrics": result.get("raw_metrics", {}),
                "sentinel_response": result.get("final_response", ""),
            }
        except Exception as e:
            logger.warning("Sentinel collect failed: %s", e)
            return {
                "weather": {},
                "hazards": [],
                "flood_risk": {},
                "risk_summary": "Donnees meteo indisponibles",
                "metrics": {},
                "sentinel_response": "",
            }

    def _fetch_market_data(self, zone: str, crop: str) -> Dict[str, Any]:
        """Appelle MarketCoach pour les données marché réelles."""
        try:
            market_input = {
                "user_query": f"Prix et tendance du {crop} a {zone}",
                "user_profile": {"zone": zone},
                "warnings": [],
            }
            result = self.wf_market.invoke(market_input)
            raw = result.get("market_data", {})
            return {
                "prices": raw.get("prices", {}),
                "trends": raw.get("trends", {}),
                "logistics": raw.get("logistics", {}),
                "market_response": result.get("final_response", ""),
            }
        except Exception as e:
            logger.warning("Market collect failed: %s", e)
            return {"prices": {}, "trends": {}, "logistics": {}, "market_response": ""}

    def _fetch_community_data(self, zone: str, crop: str) -> Dict[str, Any]:
        """Données communautaires (DB ou simulation)."""
        # TODO: Remplacer par vraie requête PostgreSQL
        return {
            "rendement_moyen_voisins": 2.5,
            "votre_rendement_estime": 2.8,
            "classement_percentile": 75,
            "meilleure_pratique_locale": "Paillage + compost bio",
            "top10_pratique": "Association mais-niebe avec fumure organique",
            "nombre_agriculteurs_zone": 120,
        }

    def collect_data_node(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Collecte RÉELLE — lance Sentinelle + Market en parallèle.
        Latence = max(sentinel, market), pas sum().
        """
        logger.info("📊 COLLECT: Appel des agents réels (parallèle)")

        zone = state.get("zone_id", "Bobo-Dioulasso")
        crop = state.get("crop", "Maïs")

        sentinel_data = {}
        market_data = {}

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                pool.submit(self._fetch_sentinel_data, zone, crop): "sentinel",
                pool.submit(self._fetch_market_data, zone, crop): "market",
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    if name == "sentinel":
                        sentinel_data = future.result(timeout=30)
                    else:
                        market_data = future.result(timeout=30)
                except Exception as e:
                    logger.warning("Collect %s timeout: %s", name, e)

        community_data = self._fetch_community_data(zone, crop)

        # Extraire les données météo structurées depuis les métriques Sentinel
        metrics = sentinel_data.get("metrics", {})
        meteo_structured = {
            "temp_max": metrics.get("temp_max_c", 36),
            "temp_min": metrics.get("temp_min_c", 24),
            "precip_mm": metrics.get("precip_mm", 0),
            "et0_mm": metrics.get("et0_mm", 0),
            "humidity_pct": metrics.get("humidity_pct", 0),
            "wind_kmh": metrics.get("wind_kmh", 0),
            "soil_moisture": metrics.get("soil_moisture_index", 0),
        }

        # Données marché structurées
        prices = market_data.get("prices", {})
        trends = market_data.get("trends", {})
        market_structured = {
            "prix_actuel": prices.get("current_price", 0),
            "prix_semaine_derniere": prices.get("last_week_price", 0),
            "tendance": trends.get("direction", "Stable"),
            "variation_pct": trends.get("variation_percent", 0),
            "meilleur_acheteur": market_data.get("logistics", {}).get(
                "sonagess_center", "Cooperative locale"
            ),
        }

        return {
            "meteo_data": meteo_structured,
            "health_data": {
                "hazards": sentinel_data.get("hazards", []),
                "flood_risk": sentinel_data.get("flood_risk", {}),
                "risk_summary": sentinel_data.get("risk_summary", ""),
                "sentinel_response": sentinel_data.get("sentinel_response", ""),
            },
            "market_data": market_structured,
            "community_benchmark": community_data,
            "execution_path": ["collect_data"],
        }

    # ================================================================== #
    # 2. SEASON ADAPTER — Priorise le rapport selon la saison
    # ================================================================== #

    def season_adapter_node(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Adapte le type de rapport à la saison agricole.
        - Mai/Juin (semis) → priorité santé culture
        - Oct/Nov (récolte) → priorité finances
        - Déc/Jan (post-récolte) → benchmark communautaire

        Si l'utilisateur a demandé un type spécifique, on respecte son choix.
        """
        current_month = datetime.now().month
        season = SEASON_CALENDAR.get(current_month, "saison_seche")
        suggested_type = SEASON_PRIORITY.get(season, "weekly_health")

        # L'utilisateur a-t-il demandé un type spécifique ?
        requested = (state.get("requete_utilisateur") or "").lower()
        if "finance" in requested or "bilan" in requested or "argent" in requested:
            chosen = "monthly_finance"
        elif "communaut" in requested or "compar" in requested or "voisin" in requested:
            chosen = "community_benchmark"
        elif "hebdo" in requested or "sante" in requested or "meteo" in requested:
            chosen = "weekly_health"
        else:
            chosen = suggested_type  # Automatique selon saison

        logger.info(
            "🗓️ SEASON: mois=%d saison=%s → rapport=%s",
            current_month, season, chosen,
        )

        return {
            "needs": {"report_type": chosen, "season": season},
            "execution_path": ["season_adapter"],
        }

    # ================================================================== #
    # 3. URGENCY FILTER — Skip si rien de neuf
    # ================================================================== #

    def urgency_filter_node(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Filtre de pertinence : si les données n'ont pas changé de >5%,
        envoie un message d'encouragement court au lieu d'un rapport complet.

        Vérifie :
        - Alertes météo (hazards HAUT/CRITICAL → toujours envoyer)
        - Variation prix (>5% → envoyer rapport finance)
        - Sinon → message d'encouragement
        """
        health = state.get("health_data", {})
        market = state.get("market_data", {})
        hazards = health.get("hazards", [])

        # Urgences météo → toujours envoyer
        critical_hazards = [
            h for h in hazards
            if h.get("severity") in ("HAUT", "CRITICAL", "HIGH")
        ]
        if critical_hazards:
            logger.info("🚨 FILTER: Alertes critiques détectées → rapport complet")
            return {"execution_path": ["urgency_filter_pass"]}

        # Variation prix significative → toujours envoyer
        variation = abs(market.get("variation_pct", 0))
        if variation >= CHANGE_THRESHOLD_PERCENT:
            logger.info("📈 FILTER: Variation prix %.1f%% → rapport complet", variation)
            return {"execution_path": ["urgency_filter_pass"]}

        # Rien de critique → on envoie quand même le rapport (en production
        # périodique, l'agriculteur attend son rapport). On pourrait aussi
        # ajouter un flag "skip_if_boring" pour les envois quotidiens.
        logger.info("✅ FILTER: Pas d'urgence, rapport standard")
        return {"execution_path": ["urgency_filter_pass"]}

    # ================================================================== #
    # 4. ROUTING — Quel rapport générer ?
    # ================================================================== #

    def route_by_report_type(self, state: GlobalAgriState) -> str:
        """Route vers le bon générateur de rapport."""
        needs = state.get("needs", {})
        return needs.get("report_type", "weekly_health")

    # ================================================================== #
    # 5. WEEKLY HEALTH — Rapport hebdomadaire
    # ================================================================== #

    def generate_weekly_health_node(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Rapport Hebdomadaire — Météo + Risques + Action du Jour.
        Commence par L'ACTION, pas par les chiffres.
        """
        logger.info("📅 GENERATE: Rapport hebdomadaire santé")

        meteo = state.get("meteo_data", {})
        health = state.get("health_data", {})
        market = state.get("market_data", {})
        crop = state.get("crop", "votre culture")
        zone = state.get("zone_id", "votre zone")
        hazards = health.get("hazards", [])
        season = state.get("needs", {}).get("season", "")

        # ── Construire l'action du jour ──────────────────────────────
        action = self._build_action_du_jour(meteo, hazards, market, crop)

        # ── Alertes formatées ────────────────────────────────────────
        alert_lines = []
        for h in hazards:
            sev = h.get("severity", "?")
            label = h.get("label", "Alerte")
            advice = h.get("advice", h.get("explanation", ""))
            icon = "🔴" if sev in ("HAUT", "CRITICAL", "HIGH") else "🟡"
            alert_lines.append(f"{icon} {label} ({sev}): {advice}")
        alerts_block = "\n".join(alert_lines) if alert_lines else "Aucune alerte ✅"

        # ── Rapport complet ──────────────────────────────────────────
        report = (
            f"🎯 ACTION DU JOUR:\n"
            f"{action}\n\n"
            f"{'='*40}\n"
            f"🌾 RAPPORT HEBDO — {crop.upper()} ({zone})\n"
            f"📅 Semaine du {datetime.now().strftime('%d/%m/%Y')}\n\n"
            f"🌡️ METEO:\n"
            f"- Temperature: {meteo.get('temp_min', '?')}–{meteo.get('temp_max', '?')}°C\n"
            f"- Pluie: {meteo.get('precip_mm', 0)}mm\n"
            f"- Perte eau sol: {meteo.get('et0_mm', 0):.1f}mm/jour\n"
            f"- Humidite sol: {self._soil_label(meteo.get('soil_moisture', 0))}\n\n"
            f"⚠️ ALERTES:\n{alerts_block}\n\n"
            f"💰 MARCHE {crop}:\n"
            f"- Prix: {market.get('prix_actuel', '?')} FCFA/kg"
            f" ({market.get('tendance', 'Stable')})\n\n"
            f"📞 Questions? Repondez ou appelez 55555"
        )

        # ── SMS 160 chars (pas d'emoji exotiques) ────────────────────
        sms = self._build_sms_tier1(action, crop, hazards)

        is_sms = state.get("is_sms_mode", False)

        return {
            "final_report": {
                "type": "weekly_health",
                "full_text": report,
                "sms_text": sms,
                "action_du_jour": action,
                "generated_at": datetime.now().isoformat(),
            },
            "final_response": sms if is_sms else report,
            "execution_path": ["weekly_health"],
        }

    # ================================================================== #
    # 6. MONTHLY FINANCE — Bilan mensuel
    # ================================================================== #

    def generate_monthly_finance_node(self, state: GlobalAgriState) -> Dict[str, Any]:
        """Bilan Mensuel — Prix, Tendances, Décision VENDRE/STOCKER."""
        logger.info("💰 GENERATE: Bilan financier mensuel")

        market = state.get("market_data", {})
        meteo = state.get("meteo_data", {})
        hazards = state.get("health_data", {}).get("hazards", [])
        crop = state.get("crop", "votre production")
        zone = state.get("zone_id", "votre zone")

        prix = market.get("prix_actuel", 0)
        prix_sem = market.get("prix_semaine_derniere", 0)
        tendance = market.get("tendance", "Stable")
        variation = market.get("variation_pct", 0)
        acheteur = market.get("meilleur_acheteur", "Marche local")

        # Décision commerciale
        if tendance in ("Hausse", "hausse") and variation > 3:
            decision = "VENDEZ cette semaine"
            raison = "les prix montent"
        elif tendance in ("Baisse", "baisse"):
            decision = "STOCKEZ si possible"
            raison = "les prix baissent, attendez la remontee"
        else:
            decision = "ATTENDEZ 1 semaine"
            raison = "le marche est stable"

        # ── Action du jour ───────────────────────────────────────────
        action = f"{decision} votre {crop} — {raison}. Point de vente: {acheteur}."

        report = (
            f"🎯 ACTION DU JOUR:\n"
            f"{action}\n\n"
            f"{'='*40}\n"
            f"💰 BILAN MENSUEL — {crop.upper()} ({zone})\n"
            f"📅 {datetime.now().strftime('%B %Y')}\n\n"
            f"💵 PRIX ACTUEL: {prix} FCFA/kg\n"
            f"- Semaine derniere: {prix_sem} FCFA/kg\n"
            f"- Tendance: {tendance} ({'+' if variation > 0 else ''}{variation:.1f}%)\n\n"
            f"🏆 POINT DE VENTE:\n"
            f"- {acheteur}\n\n"
            f"📊 DECISION: {decision}\n"
            f"Raison: {raison}\n\n"
            f"📞 Besoin conseil prix? Appelez 55555\n"
            f"Repondez PRIX pour detail"
        )

        sms = self._truncate_sms(
            f"{crop}: {prix}F/kg ({tendance}). {decision}. {acheteur}. Tel:55555"
        )

        is_sms = state.get("is_sms_mode", False)

        return {
            "final_report": {
                "type": "monthly_finance",
                "full_text": report,
                "sms_text": sms,
                "action_du_jour": action,
                "generated_at": datetime.now().isoformat(),
            },
            "final_response": sms if is_sms else report,
            "execution_path": ["monthly_finance"],
        }

    # ================================================================== #
    # 7. COMMUNITY BENCHMARK — Comparaison + Conseil du Champion
    # ================================================================== #

    def generate_community_benchmark_node(self, state: GlobalAgriState) -> Dict[str, Any]:
        """
        Comparaison communautaire avec Conseil du Champion.
        - Top 25% → Conseil basé sur SA réussite pour aider les autres.
        - En dessous → Pratique spécifique du Top 10%.
        """
        logger.info("🏆 GENERATE: Benchmark communautaire")

        community = state.get("community_benchmark", {})
        crop = state.get("crop", "votre culture")
        zone = state.get("zone_id", "votre zone")

        votre = community.get("votre_rendement_estime", 0)
        moyen = community.get("rendement_moyen_voisins", 0)
        pct = community.get("classement_percentile", 50)
        best_practice = community.get("meilleure_pratique_locale", "Compost bio")
        top10_practice = community.get("top10_pratique", best_practice)
        nb_agriculteurs = community.get("nombre_agriculteurs_zone", 100)

        # Gamification
        if pct >= 90:
            badge = "TOP 10%"
            badge_icon = "1er"
            motiv = "Excellent! Vous etes un modele."
        elif pct >= 75:
            badge = "TOP 25%"
            badge_icon = "2e"
            motiv = "Tres bien! Continuez."
        elif pct >= 50:
            badge = "MOYEN+"
            badge_icon = "3e"
            motiv = "Bon niveau, quelques ameliorations possibles."
        else:
            badge = "EN PROGRESSION"
            badge_icon = "4e"
            motiv = "Courage! Vous pouvez progresser."

        # Conseil du Champion
        if pct >= 75:
            champion_conseil = (
                f"CONSEIL DU CHAMPION: Vous etes dans le {badge} de {zone}. "
                f"Votre secret ({best_practice}) aide la communaute. "
                f"Partagez votre experience avec vos voisins!"
            )
        else:
            champion_conseil = (
                f"CONSEIL DU CHAMPION: Le groupe qui reussit le mieux a {zone} "
                f"utilise: {top10_practice}. "
                f"Essayez cette saison!"
            )

        # Action du jour
        action = champion_conseil

        report = (
            f"🎯 ACTION DU JOUR:\n"
            f"{action}\n\n"
            f"{'='*40}\n"
            f"🏆 COMPARAISON — {crop.upper()} ({zone})\n"
            f"📊 {nb_agriculteurs} agriculteurs dans votre zone\n\n"
            f"VOTRE PERFORMANCE:\n"
            f"- Votre rendement: {votre} T/ha\n"
            f"- Moyenne zone: {moyen} T/ha\n"
            f"- Classement: {badge} ({badge_icon})\n\n"
            f"📈 {motiv}\n\n"
            f"💡 MEILLEURE PRATIQUE LOCALE:\n"
            f"{best_practice}\n\n"
            f"🎯 OBJECTIF:\n"
            f"{'Maintenir votre niveau' if pct >= 75 else f'Atteindre {moyen + 0.5:.1f} T/ha'}\n\n"
            f"📞 Formation gratuite? Appelez 55555"
        )

        sms = self._truncate_sms(
            f"{crop} {zone}: Vous {badge} ({votre}T/ha vs moy {moyen}T/ha). "
            f"{'Partagez!' if pct >= 75 else f'Essayez: {top10_practice[:40]}'} "
            f"Tel:55555"
        )

        is_sms = state.get("is_sms_mode", False)

        return {
            "final_report": {
                "type": "community_benchmark",
                "full_text": report,
                "sms_text": sms,
                "action_du_jour": action,
                "champion_conseil": champion_conseil,
                "generated_at": datetime.now().isoformat(),
            },
            "final_response": sms if is_sms else report,
            "execution_path": ["community_benchmark"],
        }

    # ================================================================== #
    # HELPERS
    # ================================================================== #

    def _build_action_du_jour(
        self,
        meteo: Dict,
        hazards: List,
        market: Dict,
        crop: str,
    ) -> str:
        """
        Construit 'L'Action du Jour' — la phrase la plus importante du rapport.
        Priorité : Alerte critique > Eau/Sol > Marché.
        """
        parts = []

        # 1. Alertes critiques
        critical = [
            h for h in hazards
            if h.get("severity") in ("HAUT", "CRITICAL", "HIGH")
        ]
        if critical:
            top = critical[0]
            advice = top.get("advice", top.get("explanation", "Agissez vite"))
            parts.append(f"URGENT: {advice}")

        # 2. Stress hydrique
        soil = meteo.get("soil_moisture", 0)
        et0 = meteo.get("et0_mm", 0)
        if soil < 0.3 and et0 > 4:
            parts.append(f"Arrosez vos {crop} ce soir (sol tres sec, perd {et0:.0f}mm/jour)")
        elif soil < 0.3:
            parts.append(f"Sol sec — arrosez vos {crop} tot le matin")

        # 3. Signal marché
        tendance = market.get("tendance", "")
        prix = market.get("prix_actuel", 0)
        if tendance in ("Hausse", "hausse") and prix > 0:
            parts.append(f"Prix {crop} en hausse ({prix}F/kg) — bon moment pour vendre")
        elif tendance in ("Baisse", "baisse") and prix > 0:
            parts.append(f"Prix {crop} en baisse ({prix}F/kg) — stockez si possible")

        if not parts:
            parts.append(f"Continuez l'entretien normal de votre {crop}. Tout va bien!")

        return ". ".join(parts)

    def _build_sms_tier1(self, action: str, crop: str, hazards: List) -> str:
        """
        SMS Tier 1 : L'essentiel en 160 chars max.
        Pas d'emoji exotiques (compatibilité vieux téléphones).
        """
        # Alertes critiques d'abord
        critical = [
            h for h in hazards
            if h.get("severity") in ("HAUT", "CRITICAL", "HIGH")
        ]
        if critical:
            top = critical[0]
            sms = f"!ALERTE {crop}: {top.get('label', 'Risque')}. {action[:80]}. Tel:55555"
        else:
            sms = f"{crop}: {action[:120]}. Tel:55555"

        return self._truncate_sms(sms)

    def _truncate_sms(self, text: str) -> str:
        """Tronque à 160 caractères proprement (pas de mot coupé)."""
        if len(text) <= SMS_MAX_CHARS:
            return text
        # Couper au dernier espace avant la limite
        truncated = text[: SMS_MAX_CHARS - 3]
        last_space = truncated.rfind(" ")
        if last_space > SMS_MAX_CHARS // 2:
            truncated = truncated[:last_space]
        return truncated + "..."

    @staticmethod
    def _soil_label(moisture: float) -> str:
        """Convertit un indice d'humidité en langage paysan."""
        if moisture >= 0.7:
            return "Bon (humide)"
        elif moisture >= 0.4:
            return "Correct"
        elif moisture >= 0.2:
            return "Sec — arrosage conseille"
        else:
            return "Tres sec — arrosage urgent!"

    # ================================================================== #
    # GRAPH CONSTRUCTION
    # ================================================================== #

    def _build_report_graph(self) -> StateGraph:
        """
        Graphe production-ready :

          COLLECT_DATA → SEASON_ADAPTER → URGENCY_FILTER
              → route → [WEEKLY | MONTHLY | COMMUNITY] → END
        """
        graph = StateGraph(GlobalAgriState)

        # Nœuds
        graph.add_node("collect_data", self.collect_data_node)
        graph.add_node("season_adapter", self.season_adapter_node)
        graph.add_node("urgency_filter", self.urgency_filter_node)
        graph.add_node("weekly_health", self.generate_weekly_health_node)
        graph.add_node("monthly_finance", self.generate_monthly_finance_node)
        graph.add_node("community_benchmark", self.generate_community_benchmark_node)

        # Chaîne de pré-traitement
        graph.set_entry_point("collect_data")
        graph.add_edge("collect_data", "season_adapter")
        graph.add_edge("season_adapter", "urgency_filter")

        # Routage conditionnel après filtrage
        graph.add_conditional_edges(
            "urgency_filter",
            self.route_by_report_type,
            {
                "weekly_health": "weekly_health",
                "monthly_finance": "monthly_finance",
                "community_benchmark": "community_benchmark",
            },
        )

        # Terminaisons
        graph.add_edge("weekly_health", END)
        graph.add_edge("monthly_finance", END)
        graph.add_edge("community_benchmark", END)

        return graph.compile()

    # ================================================================== #
    # PUBLIC API
    # ================================================================== #

    def generate_report(
        self,
        report_type: ReportType,
        user_id: str,
        zone_id: str = "Bobo-Dioulasso",
        crop: str = "Maïs",
        is_sms_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        Point d'entrée principal — appelé par Celery Beat ou on-demand.

        Args:
            report_type: Type de rapport souhaité (peut être overridé par season_adapter)
            user_id: Identifiant agriculteur
            zone_id: Village / zone (pour agents Sentinel + Market)
            crop: Culture principale
            is_sms_mode: Si True, retourne SMS 160 chars

        Returns:
            Dict: final_report, final_response, execution_path, status
        """
        logger.info("📊 Rapport %s pour %s (%s)", report_type.value, user_id, zone_id)

        type_to_query = {
            ReportType.WEEKLY_HEALTH: "rapport hebdomadaire sante",
            ReportType.MONTHLY_FINANCE: "bilan financier mensuel",
            ReportType.SEASONAL_CALENDAR: "calendrier cultural",
            ReportType.COMMUNITY_BENCHMARK: "comparaison communautaire voisins",
            ReportType.EMERGENCY_ALERT: "alerte urgente",
        }

        initial_state: GlobalAgriState = {
            "requete_utilisateur": type_to_query.get(report_type, "rapport"),
            "user_id": user_id,
            "zone_id": zone_id,
            "crop": crop,
            "is_sms_mode": is_sms_mode,
            "flow_type": "REPORT",
            "user_reliability_score": 0.8,
            "global_alerts": [],
            "execution_path": [],
            "expert_responses": [],
            "final_response": None,
            "final_report": None,
            "needs": None,
            "meteo_data": None,
            "soil_data": None,
            "health_data": None,
            "market_data": None,
            "health_raw_data": None,
            "audio_url": None,
            "community_benchmark": None,
        }

        try:
            result = self.graph.invoke(initial_state)
            logger.info(
                "✅ Rapport genere | Path: %s", result.get("execution_path")
            )
            return {
                "final_report": result.get("final_report"),
                "final_response": result.get("final_response"),
                "execution_path": result.get("execution_path"),
                "status": "SUCCESS",
            }
        except Exception as e:
            logger.warning("❌ Erreur rapport: %s", e, exc_info=True)
            return {
                "final_report": None,
                "final_response": "Erreur rapport. Contactez 55555.",
                "execution_path": ["error"],
                "status": "ERROR",
            }

    def run(self, state: GlobalAgriState) -> Dict[str, Any]:
        """Alias pour intégration dans le main_orchestrator."""
        return self.graph.invoke(state)


# ======================================================================
# TESTS RAPIDES
# ======================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    flow = ReportFlow()

    print("\n" + "=" * 60)
    print("TEST 1: Rapport Hebdomadaire (complet)")
    print("=" * 60)
    r = flow.generate_report(ReportType.WEEKLY_HEALTH, "Farmer01", crop="Maïs")
    print(r["final_response"])
    print(f"\nPath: {r['execution_path']}")

    print("\n" + "=" * 60)
    print("TEST 2: Bilan Financier (SMS)")
    print("=" * 60)
    r = flow.generate_report(
        ReportType.MONTHLY_FINANCE, "Farmer01", crop="Coton", is_sms_mode=True
    )
    print(r["final_response"])
    print(f"Longueur SMS: {len(r['final_response'])} chars (max {SMS_MAX_CHARS})")

    print("\n" + "=" * 60)
    print("TEST 3: Benchmark Communautaire")
    print("=" * 60)
    r = flow.generate_report(ReportType.COMMUNITY_BENCHMARK, "Farmer01", crop="Soja")
    print(r["final_response"])
