import logging
import time
import sys
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.services.scraper import ScraperOrchestrator
from backend.orchestrator.report_flow import DailyReportFlow
from backend.orchestrator.state import GlobalAgriState

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AgConnect.Scheduler")

def run_morning_alerts():
    """
    Génère et envoie les bulletins quotidiens (07:00).
    Vérifie spécifiquement les DANGERS IMMÉDIATS (Météo/Communauté).
    """
    logger.info("📡 Starting Morning Alert Broadcast...")
    
    # Simulation d'une liste d'abonnés (en prod: DB)
    subscribers = [
        {"user_id": "user_123", "zone": "Ouagadougou", "crop": "Maïs", "sms": True},
        {"user_id": "user_456", "zone": "Bobo-Dioulasso", "crop": "Coton", "sms": False}
    ]
    
    flow = DailyReportFlow()
    
    for sub in subscribers:
        try:
            # 1. Préparation de l'état initial
            # Note: Ici on pourrait injecter des données météo réelles venant du Scraper
            state: GlobalAgriState = {
                "zone_id": sub["zone"],
                "user_id": sub["user_id"],
                "crop": sub["crop"],
                "is_sms_mode": sub["sms"],
                "user_reliability_score": 0.8,
                "requete_utilisateur": None,
                "flow_type": "REPORT",
                "global_alerts": [],
                "meteo_data": None,
                "market_data": None,
                "soil_data": None,
                "health_data": None,
                "health_raw_data": None,
                "execution_path": [],
                "final_report": None,
                "final_response": None
            }
            
            # 2. Exécution du flux de danger
            logger.info(f"Checking safety for {sub['user_id']} ({sub['zone']})...")
            # Utilisation directe du compilé graph
            app = flow.build_graph()
            result = app.invoke(state)
            
            # 3. Analyse du résultat (Danger présent ?)
            report = result.get("final_report", {})
            priority = report.get("priority", "NORMAL")
            content = report.get("content", "")
            
            if priority == "URGENT":
                logger.warning(f"🚨 DANGER DETECTED for {sub['user_id']}! Sending IMMEDIATE ALERT.")
                # TODO: Connexion API SMS réelle ici
            else:
                logger.info(f"✅ Safe conditions for {sub['user_id']}. Sending standard advise.")
                
            logger.info(f"📢 SENT to {sub['user_id']}: {content[:50]}...")
            
        except Exception as e:
            logger.error(f"❌ Failed to process user {sub['user_id']}: {e}")

def run_daily_pipeline():
    logger.info("⏰ Starting Daily Ingestion Pipeline...")
    try:
        # 1. Scrape Data
        orchestrator = ScraperOrchestrator(headless=True)
        report = orchestrator.run_all(save_report=True)
        
        # 2. Ingest to RAG
        if report.get("overall_status") != "FAILURE":
            scraped_data = []
            # Flatten results from different pipelines
            raw_pipelines = report.get("data_pipelines", {})
            for pipeline_name, result in raw_pipelines.items():
                if result.get("status") == "SUCCESS":
                    items = result.get("results", [])
                    logger.info(f"Using {len(items)} items from {pipeline_name}")
                    scraped_data.extend(items)
            
            if scraped_data:
                logger.info(f"📥 Ingesting {len(scraped_data)} items into Vector Store...")
                ingestor = DataIngestor()
                ingestor.ingest_data_from_orchestrator(scraped_data)
                logger.info("✅ Ingestion complete.")
            else:
                logger.warning("⚠️ No data collected to ingest.")
        else:
            logger.error("❌ Scraping failed. Skipping ingestion.")
            
    except Exception as e:
        logger.error(f"❌ Pipeline failed: {e}", exc_info=True)

def start_scheduler():
    scheduler = BackgroundScheduler()
    
    # 1. Scraper les nouvelles données (06:00)
    scheduler.add_job(run_daily_pipeline, CronTrigger(hour=6, minute=0), id="daily_ingest")
    
    # 2. Envoyer les alertes aux fermiers (07:00) - Après avoir scanné les dangers
    scheduler.add_job(run_morning_alerts, CronTrigger(hour=7, minute=0), id="morning_alerts")
    
    logger.info("⏳ Scheduler started. Jobs: [Ingest 06:00, Alerts 07:00]")
    scheduler.start()
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("Scheduler shutdown.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--now":
        logger.info("🧪 Test Run (Immediate)...")
        run_daily_pipeline()
    else:
        start_scheduler()
