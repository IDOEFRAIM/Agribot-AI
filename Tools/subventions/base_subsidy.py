import random
import logging
import json
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from datetime import datetime

@dataclass
class MarketPrice:
    crop: str
    base_price_harvest: int
    peak_price_soudure: int
    local_demand: str
    export_potential: str
    is_regulated: bool

class AgrimarketTool:
    def __init__(self, data_path: str = "market_data.json"):
        self.logger = logging.getLogger("AgrimarketTool")
        self.data_path = data_path
        self._MARKET_DATA = self._load_market_data()
        self._OFFERS_FILE = 'market_offers.json'

    def _load_market_data(self) -> Dict[str, MarketPrice]:
        # Données de base harmonisées
        default_market = {
            "maize": MarketPrice("Maize", 150, 250, "High", "Medium", False),
            "sorghum": MarketPrice("Sorghum", 160, 260, "High", "Low", False),
            "sesame": MarketPrice("Sesame", 500, 850, "Medium", "Very High", False),
            "cotton": MarketPrice("Cotton", 300, 300, "Low", "Total", True)
        }
        
        if not os.path.exists(self.data_path):
            return default_market

        try:
            with open(self.data_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {k.lower(): MarketPrice(**v) for k, v in data.items()}
        except Exception as e:
            self.logger.error(f"Error loading prices: {e}")
            return default_market

    # ======================================================================
    # FIXED METHOD: list_offers with English Keys
    # ======================================================================
    def list_offers(self, offer_type: str = "ACHAT") -> List[Dict[str, Any]]:
        """
        Lists available market offers.
        Uses English keys to match the Agent's expectations.
        """
        if not os.path.exists(self._OFFERS_FILE):
            # Default mock data with English keys: 'product', 'price_per_kg', 'location'
            return [
                {
                    "id": 1, 
                    "type": "ACHAT", 
                    "product": "Maize", 
                    "quantity": "5 tons", 
                    "price_per_kg": 175, 
                    "location": "Ouagadougou"
                },
                {
                    "id": 2, 
                    "type": "ACHAT", 
                    "product": "Sesame", 
                    "quantity": "2 tons", 
                    "price_per_kg": 650, 
                    "location": "Bobo-Dioulasso"
                }
            ] if offer_type == "ACHAT" else []

        try:
            with open(self._OFFERS_FILE, 'r', encoding='utf-8') as f:
                all_offers = json.load(f)
                # Ensure we filter by type and return consistent keys
                return [o for o in all_offers if o.get('type') == offer_type.upper()]
        except Exception as e:
            self.logger.error(f"Error reading offers file: {e}")
            return []

    def get_market_prices(self) -> Dict[str, Any]:
        """Retourne les prix actuels avec analyse de tendance saisonnière."""
        prices = {}
        current_month = datetime.now().month
        
        for crop_key, data in self._MARKET_DATA.items():
            if 6 <= current_month <= 8:
                price = data.peak_price_soudure
                trend = "HAUSSE (Soudure)"
            elif 9 <= current_month <= 11:
                price = data.base_price_harvest
                trend = "BAISSE (Récolte)"
            else:
                price = (data.base_price_harvest + data.peak_price_soudure) // 2
                trend = "STABLE"
            
            prices[data.crop] = {
                "price": f"{price} FCFA/kg",
                "trend": trend,
                "is_regulated": data.is_regulated
            }
        return prices

    def check_price_fairness(self, crop_name: str, offered_price: float, quantity_kg: float = 100) -> Dict[str, Any]:
        """
        [PILIER 1 & 2] Vérifie si le prix proposé est juste par rapport au marché.
        Lutte contre la spéculation (Transparence).
        """
        crop_key = crop_name.lower().strip()
        data = self._MARKET_DATA.get(crop_key)
        
        if not data:
             return {"status": "UNKNOWN", "message": "Culture inconnue"}

        current_month = datetime.now().month
        # Détermination du prix de référence du marché local
        if 9 <= current_month <= 11:
             ref_price = data.base_price_harvest
        elif 6 <= current_month <= 8:
             ref_price = data.peak_price_soudure
        else:
             ref_price = (data.base_price_harvest + data.peak_price_soudure) // 2

        # Comparaison
        diff_percent = ((offered_price - ref_price) / ref_price) * 100
        
        status = "FAIR"
        advice = "Le prix est aligné avec le marché."
        
        if diff_percent < -15:
            status = "LOWBALL" # Prix cassé (Arnaque spéculateur)
            loss = (ref_price - offered_price) * quantity_kg
            advice = f"🚨 ATTENTION : Ce prix est {abs(int(diff_percent))}% sous la moyenne ! Vous perdez {int(loss)} FCFA sur ce lot. Ne vendez pas si possible."
        elif diff_percent > 15:
            status = "PREMIUM"
            advice = "✅ Excellente offre ! Au-dessus du marché."

        return {
            "market_ref_price": ref_price,
            "offered_price": offered_price,
            "status": status,
            "advice": advice,
            "difference_percent": round(diff_percent, 1)
        }

    def analyze_market_timing(self, crop_name: str, quantity_kg: float = 1000) -> Dict[str, Any]:
        """
        [PILIER 2] Analyse Warrantage (Stockage).
        Calcule le gain financier concret du stockage.
        CoT: Explique POURQUOI stocker en chiffrant le gain.
        """
        crop_key = crop_name.lower().strip()
        data = self._MARKET_DATA.get(crop_key)
        current_month = datetime.now().month
        
        if not data:
            return {"status": "Erreur", "message": "Culture non répertoriée."}

        # Logique : Stocker est rentable si le prix n'est pas régulé et qu'on est en période de récolte
        should_store = not data.is_regulated and (9 <= current_month <= 12 or 1 <= current_month <= 2)
        
        potential_gain = 0
        if should_store:
            # Gain projeté = (Prix Soudure - Prix Récolte) * Quantité - (Coût stockage ~10%)
            price_delta = data.peak_price_soudure - data.base_price_harvest
            gross_gain = price_delta * quantity_kg
            storage_cost = gross_gain * 0.15 # 15% pour le magasinage/pertes
            potential_gain = int(gross_gain - storage_cost)

        warrantage_status = "CONSEILLÉ" if should_store else "NON PRIORITAIRE"
        
        conseil_text = (
            f"Stockez maintenant ! Le sac passera de {data.base_price_harvest} à {data.peak_price_soudure} FCFA.\n"
            f"💰 GAIN ESTIMÉ : +{potential_gain} FCFA pour {quantity_kg}kg (net de frais)."
        ) if should_store else "Vente immédiate recommandée pour la trésorerie ou prix stable."

        return {
            "culture": data.crop,
            "etat_actuel": "Récolte/Abondance" if should_store else "Soudure/Haute Saison",
            "warrantage": warrantage_status,
            "conseil": conseil_text,
            "gain_potentiel_stockage": potential_gain
        }

    def calculate_profitability(self, crop_name: str, surface_ha: float, yield_kg_ha: float, total_costs: float) -> Dict[str, Any]:
        """Calcule le bénéfice net et le prix de revient."""
        crop_key = crop_name.lower().strip()
        data = self._MARKET_DATA.get(crop_key)
        if not data: return {"error": "Données manquantes"}

        total_production = surface_ha * yield_kg_ha
        avg_sale_price = (data.base_price_harvest + data.peak_price_soudure) / 2
        
        revenue = total_production * avg_sale_price
        profit = revenue - total_costs
        break_even = total_costs / total_production if total_production > 0 else 0

        return {
            "production_totale": f"{total_production} kg",
            "chiffre_affaires": f"{int(revenue)} FCFA",
            "benefice_net": f"{int(profit)} FCFA",
            "seuil_rentabilite_kg": f"{int(break_even)} FCFA/kg",
            "resultat": "BÉNÉFICIAIRE" if profit > 0 else "DÉFICITAIRE"
        }

    def get_subsidy_status(self, region: str) -> str:
        """Affiche les alertes de prix subventionnés par l'État."""
        return (
            f"📢 **ALERTE SUBVENTION - {region.upper()}**\n"
            f"- Engrais NPK : 12 000 FCFA le sac (Prix subventionné).\n"
            f"- Semences : Disponibles à la Direction Régionale.\n"
            f"- **Action :** Présentez votre carte de producteur RGA."
        )