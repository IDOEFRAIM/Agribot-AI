import math
from datetime import datetime
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

class SoilType(Enum):
    SABLEUX = {"name": "sableux", "ru_max": 60}      # 60mm/m
    ARGILEUX = {"name": "argileux", "ru_max": 180}    # 180mm/m
    LIMONNEUX = {"name": "limonneux", "ru_max": 120}  # 120mm/m
    FERRUGINEUX = {"name": "ferrugineux", "ru_max": 80} # Typique Sahel
    STANDARD = {"name": "standard", "ru_max": 100}

@dataclass(frozen=True)
class CropProfile:
    name: str
    t_base: float
    t_max_optimal: float
    # Stages en jours: (Initial, Développement, Mi-saison, Fin)
    stages: Tuple[int, int, int, int] 
    # Coefficients Kc: (ini, mid, end)
    kc_values: Tuple[float, float, float]
    drought_sensitive: bool

class SahelAgroMath:
    @staticmethod
    def calculate_hargreaves_et0(t_min: float, t_max: float, lat: float, doy: Optional[int] = None) -> float:
        if doy is None:
            doy = datetime.now().timetuple().tm_yday

        latitude_radian = math.radians(lat)
        
        # Correction de l'orbite terrestre
        dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365.0)
        # Déclinaison solaire
        delta = 0.409 * math.sin(2 * math.pi * doy / 365.0 - 1.39)
        
        # Angle horaire
        x = -math.tan(latitude_radian) * math.tan(delta)
        omega_s = math.acos(max(-1.0, min(1.0, x)))

        # Rayonnement Ra
        ra = (24 * 60 / math.pi) * 0.082 * dr * (
            omega_s * math.sin(latitude_radian) * math.sin(delta) +
            math.cos(latitude_radian) * math.cos(delta) * math.sin(omega_s)
        )

        t_mean = (t_max + t_min) / 2
        # Hargreaves-Samani
        et0 = 0.0023 * 0.408 * ra * (t_mean + 17.8) * math.sqrt(max(0, t_max - t_min))
        return round(et0, 2)

    @staticmethod
    def calculate_vpd(temp: float, rh: float) -> float:
        """Calcule le Déficit de Pression de Vapeur (VPD) en kPa."""
        es = 0.6108 * math.exp((17.27 * temp) / (temp + 237.3))
        ea = es * (rh / 100)
        return round(es - ea, 2)

    @staticmethod
    def calculate_delta_t(temp: float, rh: float) -> Tuple[float, str]:
        # Formule de Stull pour Tw
        tw = (temp * math.atan(0.151977 * math.sqrt(rh + 8.313659)) + 
              math.atan(temp + rh) - math.atan(rh - 1.676331) + 
              0.00391838 * (rh**1.5) * math.atan(0.023101 * rh) - 4.686035)
        
        delta_t = round(temp - tw, 1)
        
        if 2 <= delta_t <= 8: advice = "OPTIMAL"
        elif delta_t > 10: advice = "DANGER_EVAPORATION"
        else: advice = "RISQUE_LESSIVAGE"
        return delta_t, advice

class SahelAgriAdvisor:
    def __init__(self):
        self.math = SahelAgroMath()
        self.crops = {
            "maïs": CropProfile("Maïs", 10, 35, (20, 35, 40, 30), (0.3, 1.2, 0.6), True),
            "mil": CropProfile("Mil", 12, 42, (20, 30, 40, 20), (0.3, 1.0, 0.5), False),
            "niébé": CropProfile("Niébé", 12, 36, (15, 25, 25, 10), (0.4, 1.0, 0.3), False)
        }

    def _get_dynamic_kc(self, crop: CropProfile, dap: int) -> float:
        """Calcule le Kc selon le stade de croissance (interpolation linéaire)."""
        L1, L2, L3, L4 = crop.stages
        Kini, Kmid, Kend = crop.kc_values
        
        if dap <= L1:
            return Kini
        elif dap <= (L1 + L2):
            return Kini + (dap - L1) / L2 * (Kmid - Kini)
        elif dap <= (L1 + L2 + L3):
            return Kmid
        elif dap <= (L1 + L2 + L3 + L4):
            return Kmid + (dap - (L1 + L2 + L3)) / L4 * (Kend - Kmid)
        else:
            return Kend

    def _compute_confiance(self, distance_km: float) -> Tuple[str, str]:
        if distance_km < 10: return "🟢", "Confiance élevée"
        if distance_km < 30: return "🟠", "Confiance moyenne"
        return "🔴", "Confiance faible (Station éloignée)"

    def get_daily_diagnosis(self, 
                           crop_key: str, 
                           soil: SoilType, 
                           t_min: float, 
                           t_max: float, 
                           rh: float, 
                           precip: float, 
                           dap: int, # Jours après semis
                           lat: float,
                           distance_km: float = 0.0,
                           wind_speed: float = 0.0) -> dict:
        
        crop = self.crops.get(crop_key.lower())
        if not crop: return {"error": "Culture non reconnue"}

        # 1. Calculs de base
        et0 = self.math.calculate_hargreaves_et0(t_min, t_max, lat)
        current_kc = self._get_dynamic_kc(crop, dap)
        etc = round(et0 * current_kc, 2)
        vpd = self.math.calculate_vpd(t_max, rh)
        
        # 2. Bilan hydrique simplifié du jour
        pe = self._calculate_pe(precip, soil)
        water_balance = round(pe - etc, 2)

        # 3. Alertes
        delta_t, spray_status = self.math.calculate_delta_t(t_max, rh)
        
        operational_alerts = []
        if vpd > 2.5:
            operational_alerts.append({"action": "ATTENTION", "target": "Plante", "reason": "Stress thermique (VPD élevé), la plante ferme ses stomates."})
        if wind_speed > 20:
            operational_alerts.append({"action": "STOP", "target": "Pulvérisation", "reason": "Vent trop fort."})
        if precip > 15:
            operational_alerts.append({"action": "STOP", "target": "Fertilisation", "reason": "Risque de lessivage."})

        emoji, conf_txt = self._compute_confiance(distance_km)

        return {
            "culture": crop.name,
            "stade_dap": dap,
            "kc_actuel": current_kc,
            "besoin_eau_mm": etc,
            "bilan_jour": water_balance,
            "vpd_kPa": vpd,
            "delta_t": delta_t,
            "pulverisation": spray_status,
            "fiabilite": f"{emoji} {conf_txt}",
            "alerts": operational_alerts
        }

    def _calculate_pe(self, rain: float, soil: SoilType) -> float:
        # On utilise ici le TAW (Total Available Water) du sol pour pondérer
        soil_retention = soil.value['ru_max'] / 100 
        pe = rain * 0.8 # Base de 80% d'efficacité au Sahel
        return round(pe * soil_retention, 2)