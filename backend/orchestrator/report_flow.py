import logging
import json
from datetime import datetime
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage
from groq_client import client

from orchestrator.state import GlobalAgriState, Alert, Severity
from tools.meteo.basis_tools import SahelAgriAdvisor, SoilType 
from agents.agri_business_coach import AgriBusinessCoach
from tools.collaboration.alert_reporter import AlertReporter
from utils.sms_adapter import SMSAdapter
from rag.components.vector_store import VectorStoreHandler

logger = logging.getLogger("ReportFlow")

class DailyReportFlow:
    """
    Générateur de bulletins quotidiens PROACTIFS et HOLISTIQUES.
    Incarne les 4 piliers : Météo Décisionnelle, Finance, Sécurité, Communauté.
    """
    def __init__(self, llm_client=None):
        self.meteo_advisor = SahelAgriAdvisor() # Pilier 1 & 3: Calculs froids + Alertes techniques
        self.market_agent = AgriBusinessCoach(llm_client=llm_client) # Pilier 2: Fintech & Warrantage
        self.alert_tool = AlertReporter() # Pilier 1: Communautaire
        self.vector_store = VectorStoreHandler() # Pilier 1 & 3: Intelligence externe (Scraping)
        
        # Initialisation du LLM de synthèse
        try:
            self.llm = llm_client if llm_client else client
        except Exception as e:
            logger.warning(f"Groq API non disponible pour la synthèse : {e}")
            self.llm = None

    def fetch_daily_data(self, state: GlobalAgriState) -> Dict[str, Any]:
        """Collecte les données fraîches multidimensionnelles."""
        logger.info("--- NODE: FETCHING INTEGRATED DATA ---")
        zone = state.get("zone_id", "Ouagadougou")
        crop = state.get("crop", "Maïs") # Note: 'crop' n'est pas dans GlobalAgriState standard, on utilisera un default
        
        # 1. ALERTES COMMUNAUTAIRES (Collaboration)
        # On regarde s'il y a des dangers signalés par d'autres aujourd'hui (Local DB)
        recent_events = self.alert_tool.get_recent_alerts(zone)
        # Transformation en format Alert pour le state
        new_alerts = []
        for e in recent_events:
            if e["severity"] in ["HIGH", "CRITICAL"]:
                sev = Severity.CRITICAL if e["severity"] == "CRITICAL" else Severity.HIGH
                # TypedDict ne s'instancie pas, on utilise un dict literal typé implicitement
                new_alerts.append({"source": "communauté", "message": e["description"], "severity": sev})

        # 1b. INTELLIGENCE EXTERNE (Vector Store - Scraping Inondations/Feux/Conflits)
        # Recherche directe dans les métadonnées pour les alertes récentes type "METEO_ALERT"
        try:
            # On scanne les docs de type METEO_ALERT pour la zone concernée
            # Note: Dans une vraie implémentation, on ferait une recherche vecteur "Danger [Zone]"
            # Ici, pour être déterministe, on regarde les metadata des derniers docs ajoutés
            scraped_alerts = []
            if hasattr(self.vector_store, 'metadata'):
                for meta in self.vector_store.metadata.values():
                    if meta.get("source_type") == "METEO_ALERT" and zone.lower() in str(meta).lower():
                        scraped_alerts.append(meta)
            
            for alert in scraped_alerts:
                content = alert.get("text") or alert.get("content", "Alerte détectée sans détails")
                # Éviter les doublons exacts
                if not any(a["message"] == content for a in new_alerts):
                    new_alerts.append({"source": "sentinelle_web", "message": f"WEB: {content[:100]}...", "severity": Severity.HIGH})
                    logger.warning(f"🚨 ALERTE WEB DETECTÉE: {content}")
        except Exception as e:
            logger.error(f"Erreur lecture Vector Store pour alertes: {e}")

        # 2. DIAGNOSTIC MÉTÉO DÉCISIONNEL
        # Simulation données météo (devrait venir d'une API externe ou du state précédent)
        # Si le state contient déjà des données météo (ex: via worker/crawler), on les utilise
        raw_weather = state.get("meteo_data", {}) or {
            "t_min": 24, "t_max": 36, "rh": 45, 
            "precip": 12.0, "wind_speed": 22.0, 
            "rain_prob": 60
        }
        
        # S'assurer que les clés existent, sinon défaut
        weather_params = {
            "t_min": raw_weather.get("t_min", 24),
            "t_max": raw_weather.get("t_max", 36),
            "rh": raw_weather.get("rh", 45),
            "precip": raw_weather.get("precip", 0),
            "wind_speed": raw_weather.get("wind_speed", 10),
            "rain_prob": raw_weather.get("rain_prob", 0)
        }

        meteo_diag = self.meteo_advisor.get_daily_diagnosis(
            crop_key=crop if isinstance(crop, str) else "Maïs",
            soil=SoilType.STANDARD,
            t_min=weather_params["t_min"], t_max=weather_params["t_max"], rh=weather_params["rh"],
            precip=weather_params["precip"], lat=12.37, doy=datetime.now().timetuple().tm_yday,
            wind_speed_kmh=weather_params["wind_speed"],
            rain_prob_next_6h=weather_params["rain_prob"]
        )

        # 3. INTELLIGENCE MARCHÉ (Warrantage & Prix)
        market_analysis = self.market_agent.market_tool.analyze_market_timing(
            crop if isinstance(crop, str) else "Maïs", 
            quantity_kg=1000
        )

        # Retourner les mises à jour du state
        return {
            "global_alerts": new_alerts,
            "meteo_data": {**raw_weather, "diagnosis": meteo_diag},
            "market_data": market_analysis
        }

    def generate_report(self, state: GlobalAgriState) -> Dict[str, Any]:
        """Agrège tout en un bulletin de guerre quotidien."""
        logger.info("--- NODE: GENERATING WAR ROOM REPORT ---")
        
        zone = state.get("zone_id", "Ouagadougou")
        meteo_data = state.get("meteo_data") or {}
        market_data = state.get("market_data") or {}
        alerts = state.get("global_alerts") or []
        
        diag = meteo_data.get("diagnosis", {})
        
        # Extraction contextuelle
        data_summary = {
            "community_alerts": [a["message"] for a in alerts],
            "meteo_risks": diag.get("alerts_critiques", []),
            "market_advice": market_data.get("conseil", "Surveiller les prix")
        }
        
        context_str = json.dumps(data_summary, indent=2, ensure_ascii=False, default=str)
        is_sms = state.get("is_sms_mode", False)
        
        if self.llm:
            system_prompt = (
                f"Tu es 'AgriConnect Sentinelle', le gardien de la zone {zone}. "
                "Rédige le bulletin quotidien pour les agriculteurs.\n\n"
                "STRUCTURE DU BULLETIN (Doit tenir dans ~300 caractères si possible) :\n"
                "1. 🚨 SÉCURITÉ D'ABORD : Commence par les alertes (Météo ou Communautaires). Si danger = impératif.\n"
                "2. 🚜 ACTION AUX CHAMPS : Résume les interdictions techniques (Pas d'engrais, etc).\n"
                "3. 💰 ARGENT : Donne le conseil Warrantage (ex: 'Gain +50000F si tu stockes').\n\n"
                "TON : Urgent, Protecteur, Chiffré."
            )
            
            try:
                response = self.llm.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"SITUATION DU JOUR :\n{context_str}"}
                    ],
                    temperature=0.7,
                    max_tokens=512
                )
                report_content = response.choices[0].message.content if response.choices else ""
            except Exception as e:
                report_content = "Erreur génération bulletin."
        else:
            # Fallback manuel robuste
            report_content = f"Bulletin {zone} :\n"
            if data_summary["community_alerts"]:
                report_content += f"🚨 COMMUNAUTÉ: {data_summary['community_alerts'][0]}\n"
            
            weather_risks = diag.get('alerts_critiques', [])
            if weather_risks:
                report_content += f"⚠️ METEO: {weather_risks[0]['target']} - {weather_risks[0]['reason']}\n"
            
            report_content += f"💰 WARANTAGE: {data_summary['market_advice']}"

        # --- PILIER 4: SCALABILITÉ (ADAPTATION SMS) ---
        if is_sms:
            report_content = SMSAdapter.compress_for_sms(report_content)

        # Calcul priorité pour push
        is_urgent = len(alerts) > 0 or len(diag.get("alerts_critiques", [])) > 0

        return {
            "final_report": {
                "content": report_content, 
                "priority": "URGENT" if is_urgent else "NORMAL",
                "channel": "SMS" if is_sms else "APP"
            }
        }

    def build_graph(self):
        """Compile le workflow LangGraph."""
        workflow = StateGraph(GlobalAgriState)
        workflow.add_node("fetch_data", self.fetch_daily_data)
        workflow.add_node("generate_report", self.generate_report)
        
        workflow.set_entry_point("fetch_data")
        workflow.add_edge("fetch_data", "generate_report")
        workflow.add_edge("generate_report", END)
        
        return workflow.compile()