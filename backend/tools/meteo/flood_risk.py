import json
import os
import logging
import math
from datetime import datetime
from typing import TypedDict, List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_community.chat_models import ChatOllama

class SoilType(Enum):
    SABLEUX = "sableux"
    ARGILEUX = "argileux"
    LIMONNEUX = "limonneux"
    FERRUGINEUX = "ferrugineux"
    STANDARD = "standard"

@dataclass(frozen=True)
class CropProfile:
    name: str
    t_base: float
    t_max_optimal: float
    kc: Dict[str, float]
    cycle_days: int
    drought_sensitive: bool

class SahelAgroMath:
    GSC = 0.0820
    @staticmethod
    def calculate_hargreaves_et0(t_min: float, t_max: float, lat: float, doy: int) -> float:
        phi = math.radians(lat)
        dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365.0)
        delta = 0.409 * math.sin(2 * math.pi * doy / 365.0 - 1.39)
        x = -math.tan(phi) * math.tan(delta)
        omega_s = math.acos(max(-1.0, min(1.0, x)))
        ra = (24 * 60 / math.pi) * 0.0820 * dr * (
            omega_s * math.sin(phi) * math.sin(delta) +
            math.cos(phi) * math.cos(delta) * math.sin(omega_s)
        )
        t_mean = (t_max + t_min) / 2
        et0 = 0.0023 * 0.408 * ra * (t_mean + 17.8) * math.sqrt(max(0, t_max - t_min))
        return round(et0, 2)

    @staticmethod
    def calculate_delta_t(temp: float, rh: float) -> Tuple[float, str]:
        tw = (temp * math.atan(0.151977 * math.sqrt(rh + 8.313659)) + 
              math.atan(temp + rh) - math.atan(rh - 1.676331) + 
              0.00391838 * (rh**1.5) * math.atan(0.023101 * rh) - 4.686035)
        delta_t = round(temp - tw, 1)
        if 2 <= delta_t <= 8: advice = "OPTIMAL"
        elif delta_t > 10: advice = "DANGER_EVAPORATION"
        else: advice = "RISQUE_LESSIVAGE"
        return delta_t, advice
    


class FloodRiskTool:
    def __init__(self):
        # Seuils basés sur les standards de l'Afrique de l'Ouest (CILSS/FANFAR)
        self.THRESHOLDS = {
            "CRITIQUE": 100.0, # mm en 24h
            "ELEVE": 60.0,     # mm en 24h
            "MODERE": 30.0     # mm en 24h
        }

    def check_flood_risk(self, 
                         lat: float, 
                         lon: float, 
                         precip_today: float, 
                         precip_3d_cumul: float, 
                         is_near_water: bool = False) -> Dict[str, Any]:
        """
        Analyse dynamique du risque d'inondation.
        Args:
            precip_today: Pluie du jour (mm)
            precip_3d_cumul: Pluie cumulée des 3 derniers jours (mm)
            is_near_water: Si le champ est dans un bas-fond ou près d'un cours d'eau
        """
        risk_score = 0
        
        # 1. Analyse de l'intensité immédiate
        if precip_today >= self.THRESHOLDS["CRITIQUE"]: risk_score = 4
        elif precip_today >= self.THRESHOLDS["ELEVE"]: risk_score = 3
        elif precip_today >= self.THRESHOLDS["MODERE"]: risk_score = 2
        elif precip_today > 0: risk_score = 1

        # 2. Facteur aggravant : Saturation des sols (Cumul 3 jours)
        # Si le sol est déjà gorgé d'eau, une petite pluie provoque une crue
        if precip_3d_cumul > 120:
            risk_score = max(risk_score, 3)
        
        # 3. Facteur aggravant : Topographie
        if is_near_water and risk_score >= 2:
            risk_score += 1 # On augmente le niveau de risque pour les bas-fonds

        risk_levels = {
            0: "Nul",
            1: "Faible",
            2: "Modéré",
            3: "Élevé",
            4: "Critique"
        }
        
        current_risk = risk_levels.get(min(risk_score, 4))
        
        return {
            "risk_level": current_risk,
            "precip_24h": precip_today,
            "soil_saturation": "Élevée" if precip_3d_cumul > 80 else "Normale",
            "alert_message": self._generate_alert_message(current_risk, is_near_water),
            "timestamp": datetime.now().isoformat()
        }

    def _generate_alert_message(self, risk: str, is_near_water: bool) -> str:
        messages = {
            "Critique": "⚠️ DANGER IMMINENT. Inondation généralisée possible. Évacuez les zones basses.",
            "Élevé": "🔴 Risque de crue soudaine. Ne traversez pas les ponts ou les radiers.",
            "Modéré": "🟠 Attention, ruissellement important. Protégez vos stocks de semences/engrais.",
            "Faible": "🟢 Vigilance normale. Les sols absorbent bien l'eau.",
            "Nul": "⚪ Aucun risque détecté."
        }
        msg = messages.get(risk, "")
        if is_near_water and risk != "Nul":
            msg += " (Zone de bas-fond : risque multiplié)"
        return msg

    def get_prevention_advice(self, risk_level: str) -> List[str]:
        advice_map = {
            "Faible": ["Vérifier le drainage des parcelles."],
            "Modéré": ["Créer des rigoles d'évacuation.", "Surélever les sacs d'engrais."],
            "Élevé": ["Arrêter toute activité de traitement.", "Mettre le bétail à l'abri sur les hauteurs."],
            "Critique": ["ÉVACUATION immédiate.", "Suivre les directives des autorités locales (CONASUR)."]
        }
        return advice_map.get(risk_level, ["Restez à l'écoute de la radio locale."])