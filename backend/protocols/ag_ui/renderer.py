"""
AG-UI Renderers — Traducteurs de composants AG-UI vers chaque canal.
=====================================================================

Chaque renderer sait transformer un AgriResponse en format natif :
  - WhatsAppRenderer : Messages interactifs Twilio WhatsApp
  - WebRenderer      : JSON enrichi pour frontend web
  - SMSRenderer      : Texte condensé pour SMS/USSD
"""

import json
import logging
from typing import Any, Dict, List
from abc import ABC, abstractmethod

from .components import (
    AGUIComponent, ComponentType, AgriResponse,
    TextBlock, Card, ActionButton, ListPicker, FormField, ChartData, AlertBanner,
    Severity, ActionType,
)

logger = logging.getLogger("AG-UI.Renderer")


# ═══════════════════════════════════════════════════════════════
# BASE RENDERER
# ═══════════════════════════════════════════════════════════════

class AGUIRenderer(ABC):
    """Renderer de base — Interface pour tous les canaux."""

    @abstractmethod
    def render(self, response: AgriResponse) -> Any:
        """Transforme un AgriResponse en format natif du canal."""
        ...

    @abstractmethod
    def render_component(self, component: AGUIComponent) -> Any:
        """Transforme un composant individuel."""
        ...


# ═══════════════════════════════════════════════════════════════
# WHATSAPP RENDERER (via Twilio Business API)
# ═══════════════════════════════════════════════════════════════

class WhatsAppRenderer(AGUIRenderer):
    """
    Traduit les composants AG-UI en format WhatsApp interactif.
    
    Mapping :
      TextBlock   → Message texte standard
      Card        → Message formaté + image (si disponible)
      ActionButton → Bouton interactif WhatsApp (max 3 boutons)
      ListPicker  → Liste interactive WhatsApp (max 10 items)
      FormField   → Question interactive
      ChartData   → Image générée (export matplotlib/plotly)
      AlertBanner → Message d'alerte avec emojis
    """

    SEVERITY_EMOJI = {
        Severity.INFO: "ℹ️",
        Severity.WARNING: "⚠️",
        Severity.HIGH: "🔴",
        Severity.CRITICAL: "🚨",
    }

    def render(self, response: AgriResponse) -> Dict[str, Any]:
        """Génère un payload Twilio WhatsApp complet."""
        messages = []

        for component in response.components:
            rendered = self.render_component(component)
            if rendered:
                messages.append(rendered)

        return {
            "channel": "whatsapp",
            "messages": messages,
            "voice_summary": response.voice_summary,
            "fallback_text": response.raw_text or self._build_fallback(response),
        }

    def render_component(self, component: AGUIComponent) -> Dict[str, Any]:
        handlers = {
            ComponentType.TEXT: self._render_text,
            ComponentType.CARD: self._render_card,
            ComponentType.ACTION: self._render_action,
            ComponentType.LIST_PICKER: self._render_list_picker,
            ComponentType.FORM_FIELD: self._render_form_field,
            ComponentType.CHART: self._render_chart,
            ComponentType.ALERT: self._render_alert,
        }
        handler = handlers.get(component.type)
        if handler:
            return handler(component)
        return None

    def _render_text(self, block: TextBlock) -> Dict:
        return {"type": "text", "body": block.content}

    def _render_card(self, card: Card) -> Dict:
        # Format WhatsApp enrichi
        lines = []
        if card.severity:
            emoji = self.SEVERITY_EMOJI.get(card.severity, "📋")
            lines.append(f"{emoji} *{card.title}*")
        else:
            lines.append(f"📋 *{card.title}*")

        if card.subtitle:
            lines.append(f"_{card.subtitle}_")
        if card.body:
            lines.append(f"\n{card.body}")

        for f in card.fields:
            lines.append(f"• {f.get('label', '')}: {f.get('value', '')}")

        result = {"type": "text", "body": "\n".join(lines)}

        # Ajouter image si disponible
        if card.image_url:
            result["media_url"] = card.image_url

        # Boutons interactifs (max 3 pour WhatsApp)
        if card.actions:
            result["buttons"] = [
                {"id": a.id or f"btn_{i}", "title": a.label[:20]}  # WhatsApp: max 20 chars
                for i, a in enumerate(card.actions[:3])
            ]
            result["type"] = "interactive_buttons"

        return result

    def _render_action(self, action: ActionButton) -> Dict:
        return {
            "type": "interactive_buttons",
            "body": action.label,
            "buttons": [{"id": action.id or "action_btn", "title": action.label[:20]}],
        }

    def _render_list_picker(self, picker: ListPicker) -> Dict:
        # WhatsApp List Message (max 10 items)
        sections = [{
            "title": picker.title or "Options",
            "rows": [
                {
                    "id": item.get("id", str(i)),
                    "title": item.get("label", "")[:24],  # WhatsApp: max 24 chars
                    "description": item.get("description", "")[:72],
                }
                for i, item in enumerate(picker.items[:10])
            ],
        }]
        return {
            "type": "interactive_list",
            "body": picker.title or "Choisissez une option",
            "button_text": "Voir les options",
            "sections": sections,
        }

    def _render_form_field(self, field: FormField) -> Dict:
        return {
            "type": "text",
            "body": f"❓ {field.label}\n{field.placeholder}" if field.placeholder else f"❓ {field.label}",
        }

    def _render_chart(self, chart: ChartData) -> Dict:
        # Pour WhatsApp, on génère une image du graphique
        # Le frontend/worker doit appeler un service de rendu graphique
        return {
            "type": "chart_pending",
            "chart_data": chart.to_dict(),
            "body": f"📊 {chart.title}",
            "note": "Graphique en cours de génération...",
        }

    def _render_alert(self, alert: AlertBanner) -> Dict:
        emoji = self.SEVERITY_EMOJI.get(alert.severity, "ℹ️")
        lines = [
            f"{emoji} *ALERTE {alert.severity.value.upper()}*",
            f"*{alert.title}*",
            alert.message,
        ]
        if alert.zone:
            lines.append(f"📍 Zone: {alert.zone}")
        return {"type": "text", "body": "\n".join(lines)}

    def _build_fallback(self, response: AgriResponse) -> str:
        """Construit un texte de repli si aucun composant n'est rendu."""
        parts = []
        for comp in response.components:
            if isinstance(comp, TextBlock):
                parts.append(comp.content)
            elif isinstance(comp, Card):
                parts.append(f"{comp.title}: {comp.body}")
            elif isinstance(comp, AlertBanner):
                parts.append(f"ALERTE: {comp.title} - {comp.message}")
        return "\n".join(parts) if parts else response.voice_summary


# ═══════════════════════════════════════════════════════════════
# WEB RENDERER (JSON enrichi pour React/Vue/Dashboard)
# ═══════════════════════════════════════════════════════════════

class WebRenderer(AGUIRenderer):
    """
    Traduit les composants AG-UI en JSON enrichi pour frontend web.
    Le frontend React/Vue consomme directement ces composants.
    """

    def render(self, response: AgriResponse) -> Dict[str, Any]:
        return {
            "channel": "web",
            "agent": response.agent,
            "components": [self.render_component(c) for c in response.components],
            "voice_summary": response.voice_summary,
            "metadata": response.metadata,
        }

    def render_component(self, component: AGUIComponent) -> Dict[str, Any]:
        # Pour le web, on passe directement le JSON structuré
        return component.to_dict()


# ═══════════════════════════════════════════════════════════════
# SMS/USSD RENDERER (texte condensé pour zones rurales)
# ═══════════════════════════════════════════════════════════════

class SMSRenderer(AGUIRenderer):
    """
    Traduit les composants AG-UI en texte condensé pour SMS/USSD.
    
    Contraintes :
      - SMS : max 160 caractères par segment
      - USSD : max 182 caractères par écran
      - Pas d'images, pas de boutons interactifs
      - Menus numérotés : "1.Maïs 2.Sorgho 3.Mil"
    """

    MAX_SMS_LENGTH = 160
    MAX_USSD_LENGTH = 182

    def render(self, response: AgriResponse) -> Dict[str, Any]:
        segments = []
        for comp in response.components:
            text = self.render_component(comp)
            if text:
                segments.append(text)

        full_text = "\n".join(segments)

        # Découpage en segments SMS
        sms_segments = self._split_sms(full_text)

        return {
            "channel": "sms",
            "segments": sms_segments,
            "full_text": full_text,
            "segment_count": len(sms_segments),
        }

    def render_component(self, component: AGUIComponent) -> str:
        handlers = {
            ComponentType.TEXT: self._render_text,
            ComponentType.CARD: self._render_card,
            ComponentType.ACTION: self._render_action,
            ComponentType.LIST_PICKER: self._render_list,
            ComponentType.ALERT: self._render_alert,
            ComponentType.CHART: self._render_chart,
        }
        handler = handlers.get(component.type)
        return handler(component) if handler else ""

    def _render_text(self, block: TextBlock) -> str:
        # Privilégier voice_text (plus court) pour SMS
        return block.voice_text or block.content

    def _render_card(self, card: Card) -> str:
        parts = [card.title]
        if card.body:
            parts.append(card.body[:100])
        for f in card.fields[:3]:
            parts.append(f"{f.get('label')}: {f.get('value')}")
        return " | ".join(parts)

    def _render_action(self, action: ActionButton) -> str:
        return f"→ {action.label}"

    def _render_list(self, picker: ListPicker) -> str:
        items = [f"{i+1}.{item.get('label', '')}" for i, item in enumerate(picker.items[:5])]
        return f"{picker.title}: {' '.join(items)}"

    def _render_alert(self, alert: AlertBanner) -> str:
        return f"ALERTE: {alert.title}-{alert.message}"

    def _render_chart(self, chart: ChartData) -> str:
        # Résumé textuel pour SMS
        if chart.datasets:
            ds = chart.datasets[0]
            data = ds.get("data", [])
            if data:
                return f"{chart.title}: min={min(data)}, max={max(data)}, moy={sum(data)//len(data)}"
        return chart.title

    def _split_sms(self, text: str) -> List[str]:
        """Découpe le texte en segments SMS de 160 caractères."""
        if len(text) <= self.MAX_SMS_LENGTH:
            return [text]

        segments = []
        while text:
            if len(text) <= self.MAX_SMS_LENGTH:
                segments.append(text)
                break
            # Couper au dernier espace avant la limite
            cut = text[:self.MAX_SMS_LENGTH].rfind(" ")
            if cut <= 0:
                cut = self.MAX_SMS_LENGTH
            segments.append(text[:cut])
            text = text[cut:].lstrip()

        return segments
