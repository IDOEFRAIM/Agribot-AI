import operator
from typing import TypedDict, Annotated, List, Dict, Any, Union, Optional
from enum import Enum

class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class Alert(TypedDict):
    source: str
    message: str
    severity: Severity

class GlobalAgriState(TypedDict):
    # --- Context ---
    zone_id: str
    requete_utilisateur: Optional[str] # Optionnel car peut être un rapport auto
    user_id: str = "anonymous"
    user_reliability_score: float = 0.5 # Pilier 2 - Note de confiance (0.0 à 1.0)
    is_sms_mode: bool = False # Pilier 4 - Mode SMS activé
    
    # --- Flow Control ---
    flow_type: str # "MESSAGE" ou "REPORT"
    
    # --- Data Lake (Données collectées) ---
    meteo_data: Optional[Dict[str, Any]]
    soil_data: Optional[Dict[str, Any]]
    health_data: Optional[Dict[str, Any]]
    market_data: Optional[Dict[str, Any]]
    health_raw_data: Optional[Dict[str, Any]] # Input spécifique de l'utilisateur
    
    # --- Memory & Outputs ---
    global_alerts: Annotated[List[Alert], operator.add]
    execution_path: Annotated[List[str], operator.add]
    final_report: Optional[Dict[str, Any]]
    final_response: Optional[str]