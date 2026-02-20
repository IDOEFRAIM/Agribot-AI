"""
AG-UI Components — Composants structurés pour rendu multi-canal.
=================================================================

Chaque composant est un dataclass sérialisable en JSON.
Les agents construisent leur réponse avec ces composants.
Les renderers traduisent le JSON en format natif du canal.

Composants disponibles :
  - TextBlock     : Texte simple (paragraphe, conseil)
  - Card          : Fiche structurée (maladie, produit, offre)
  - ActionButton  : Bouton d'action (Vendre, Contacter, Acheter)
  - ListPicker    : Menu de sélection (cultures, zones, options)
  - FormField     : Champ de formulaire (quantité, prix)
  - ChartData     : Données pour graphique (prix, météo)
  - AlertBanner   : Bannière d'alerte (sécheresse, ravageur)
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
from enum import Enum


class ComponentType(str, Enum):
    TEXT = "text"
    CARD = "card"
    ACTION = "action"
    LIST_PICKER = "list_picker"
    FORM_FIELD = "form_field"
    CHART = "chart"
    ALERT = "alert"
    USER_APPROVAL = "user_approval"    # HITL — Demande de validation humaine
    CONTEXT_REQUEST = "context_request" # Context Elicitation — Champs manquants


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class ActionType(str, Enum):
    SELL = "sell"
    BUY = "buy"
    CONTACT = "contact"
    NAVIGATE = "navigate"
    CONFIRM = "confirm"
    CANCEL = "cancel"
    CALL_EXPERT = "call_expert"
    VIEW_DETAIL = "view_detail"


@dataclass
class AGUIComponent:
    """Composant de base AG-UI."""
    type: ComponentType
    id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["type"] = self.type.value
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


@dataclass
class TextBlock(AGUIComponent):
    """
    Bloc de texte simple.
    
    Rendu :
      WhatsApp → Message texte standard
      Web      → <p> avec style
      SMS      → Texte brut tronqué
    """
    type: ComponentType = ComponentType.TEXT
    content: str = ""
    format: str = "plain"  # plain | markdown | html
    voice_text: str = ""   # Version simplifiée pour TTS (agriculteurs analphabètes)

    def __post_init__(self):
        if not self.voice_text:
            self.voice_text = self.content


@dataclass
class Card(AGUIComponent):
    """
    Fiche structurée (maladie, produit, offre marché).
    
    Rendu :
      WhatsApp → Message formaté avec emojis + image
      Web      → Card Material UI / Bootstrap
      SMS      → Résumé condensé
    """
    type: ComponentType = ComponentType.CARD
    title: str = ""
    subtitle: str = ""
    body: str = ""
    image_url: str = ""
    fields: List[Dict[str, str]] = field(default_factory=list)  # [{"label": "Prix", "value": "225 FCFA/kg"}]
    actions: List["ActionButton"] = field(default_factory=list)
    severity: Optional[Severity] = None

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["actions"] = [a.to_dict() for a in self.actions]
        if self.severity:
            d["severity"] = self.severity.value
        return d


@dataclass
class ActionButton(AGUIComponent):
    """
    Bouton d'action.
    
    Rendu :
      WhatsApp → Bouton interactif WhatsApp Business API
      Web      → <button> cliquable
      SMS      → "Tapez 1 pour Vendre"
    """
    type: ComponentType = ComponentType.ACTION
    label: str = ""
    action_type: ActionType = ActionType.NAVIGATE
    payload: Dict[str, Any] = field(default_factory=dict)
    confirm_required: bool = False  # Double confirmation pour actions sensibles (achat, vente)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["action_type"] = self.action_type.value
        return d


@dataclass
class ListPicker(AGUIComponent):
    """
    Menu de sélection.
    
    Rendu :
      WhatsApp → Liste interactive WhatsApp
      Web      → Dropdown / Radio buttons
      SMS      → "Tapez 1: Maïs, 2: Sorgho, 3: Mil"
    """
    type: ComponentType = ComponentType.LIST_PICKER
    title: str = ""
    items: List[Dict[str, str]] = field(default_factory=list)  # [{"id": "1", "label": "Maïs", "description": "..."}]
    multi_select: bool = False


@dataclass
class FormField(AGUIComponent):
    """
    Champ de formulaire dynamique.
    
    Rendu :
      WhatsApp → Question interactive ("Combien de sacs ?")
      Web      → <input> avec validation
      SMS      → "Répondez avec le nombre de sacs"
    """
    type: ComponentType = ComponentType.FORM_FIELD
    label: str = ""
    field_type: str = "text"  # text | number | date | select
    placeholder: str = ""
    required: bool = True
    validation: Dict[str, Any] = field(default_factory=dict)  # {"min": 1, "max": 1000}
    options: List[str] = field(default_factory=list)  # Pour field_type="select"


@dataclass
class ChartData(AGUIComponent):
    """
    Données pour graphique.
    
    Rendu :
      WhatsApp → Image générée (matplotlib/plotly export)
      Web      → Graphique interactif (Chart.js, Plotly)
      SMS      → Résumé textuel des tendances
    """
    type: ComponentType = ComponentType.CHART
    chart_type: str = "line"  # line | bar | pie | area
    title: str = ""
    labels: List[str] = field(default_factory=list)
    datasets: List[Dict[str, Any]] = field(default_factory=list)
    # [{"label": "Prix Maïs", "data": [200, 225, 210], "color": "#4CAF50"}]


@dataclass
class AlertBanner(AGUIComponent):
    """
    Bannière d'alerte (sécheresse, ravageur, inondation).
    
    Rendu :
      WhatsApp → ⚠️ Message formaté avec emoji
      Web      → Bannière colorée en haut de page
      SMS      → "ALERTE: ..."
    """
    type: ComponentType = ComponentType.ALERT
    title: str = ""
    message: str = ""
    severity: Severity = Severity.INFO
    zone: str = ""
    expires_at: str = ""  # ISO datetime
    actions: List[ActionButton] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["severity"] = self.severity.value
        d["actions"] = [a.to_dict() for a in self.actions]
        return d


# ═══════════════════════════════════════════════════════════════
# HITL — Human-in-the-Loop (Validation Humaine)
# ═══════════════════════════════════════════════════════════════

@dataclass
class UserApproval(AGUIComponent):
    """
    Composant HITL — Fige le workflow en attendant la validation de l'utilisateur.
    
    Usage : Action risquée (épandage chimique, vente, transaction).
    L'orchestrateur persiste l'état et retourne ce composant.
    Le workflow reprend uniquement après callback utilisateur.
    
    Rendu :
      WhatsApp → Message + boutons Accepter/Refuser
      Web      → Modal de confirmation
      SMS      → "Tapez OUI pour confirmer, NON pour annuler"
    """
    type: ComponentType = ComponentType.USER_APPROVAL
    action_id: str = ""           # ID unique de l'action en attente
    action_summary: str = ""      # Description courte de l'action
    risk_level: Severity = Severity.WARNING
    requires_validation: bool = True
    payload: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 300    # 5 min par défaut
    callback_url: str = ""        # URL de callback pour la validation

    def to_dict(self) -> Dict[str, Any]:
        d = super().to_dict()
        d["risk_level"] = self.risk_level.value
        return d


# ═══════════════════════════════════════════════════════════════
# Context Elicitation — Demande de données manquantes
# ═══════════════════════════════════════════════════════════════

@dataclass
class ContextRequest(AGUIComponent):
    """
    Demande de contexte manquant à l'utilisateur.
    
    Usage : L'agent détecte qu'il manque des données critiques
    (date de semis, type de sol, etc.) et renvoie un formulaire
    adaptatif au lieu de deviner (anti-hallucination).
    
    Rendu :
      WhatsApp → Questions successives
      Web      → Formulaire pré-rempli
      SMS      → "Répondez avec votre date de semis"
    """
    type: ComponentType = ComponentType.CONTEXT_REQUEST
    missing_fields: List[Dict[str, str]] = field(default_factory=list)
    # [{"key": "soil_ph", "label": "pH du sol", "type": "number", "required": True}]
    message: str = ""  # Message explicatif pour l'utilisateur


@dataclass
class AgriResponse:
    """
    Réponse complète d'un agent, composée de multiples composants AG-UI.
    
    C'est l'objet que chaque agent retourne au lieu de texte brut.
    Le renderer adapte le rendu au canal de l'utilisateur.
    """
    agent: str = ""
    components: List[AGUIComponent] = field(default_factory=list)
    voice_summary: str = ""  # Résumé audio pour les agriculteurs analphabètes
    raw_text: str = ""       # Fallback texte brut (compatibilité)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent": self.agent,
            "components": [c.to_dict() for c in self.components],
            "voice_summary": self.voice_summary,
            "raw_text": self.raw_text,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def add(self, component: AGUIComponent):
        """Ajoute un composant à la réponse."""
        self.components.append(component)
        return self

    def add_text(self, content: str, voice_text: str = ""):
        """Raccourci pour ajouter un bloc de texte."""
        self.add(TextBlock(content=content, voice_text=voice_text))
        return self

    def add_card(self, title: str, body: str, **kwargs):
        """Raccourci pour ajouter une carte."""
        self.add(Card(title=title, body=body, **kwargs))
        return self

    def add_alert(self, title: str, message: str, severity: Severity = Severity.WARNING, **kwargs):
        """Raccourci pour ajouter une alerte."""
        self.add(AlertBanner(title=title, message=message, severity=severity, **kwargs))
        return self

    def add_action(self, label: str, action_type: ActionType, **kwargs):
        """Raccourci pour ajouter un bouton d'action."""
        self.add(ActionButton(label=label, action_type=action_type, **kwargs))
        return self

    def add_approval(self, action_id: str, action_summary: str,
                     risk_level: Severity = Severity.WARNING, **kwargs):
        """HITL — Ajoute une demande de validation humaine (fige le workflow)."""
        self.add(UserApproval(
            action_id=action_id,
            action_summary=action_summary,
            risk_level=risk_level,
            requires_validation=True,
            **kwargs,
        ))
        self.metadata["requires_validation"] = True
        self.metadata["pending_action_id"] = action_id
        return self

    def add_context_request(self, missing_fields: List[Dict[str, str]], message: str = ""):
        """Context Elicitation — Demande les données manquantes à l'utilisateur."""
        self.add(ContextRequest(
            missing_fields=missing_fields,
            message=message or "J'ai besoin de quelques informations pour vous aider au mieux.",
        ))
        self.metadata["awaiting_context"] = True
        return self
