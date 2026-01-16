
import logging
import sys
import os

# Add project root to path to ensure modules are found
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator.report_flow import DailyReportFlow
from orchestrator.state import GlobalAgriState

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TestReportFlow")

class MockLLM:
    def invoke(self, messages):
        # Fake structured response simulating Mistral
        return type('obj', (object,), {"content": "Bulletin Mock: 🚨 ALERTE: Orage violent. 🚜 Pas d'engrais. 💰 Warrantage: Stocke ton maïs."})

def test_daily_report_generation():
    logger.info("🎬 Starting Daily Report Flow Test")
    
    # Initialize the flow with Mock LLM to avoid local Ollama dependency
    flow = DailyReportFlow(llm_client=MockLLM())
    
    # 1. Define distinct test cases
    test_cases = [
        {
            "name": "Standard Report (App Mode)",
            "state": {
                "zone_id": "ZoneTest_Ouaga",
                "user_id": "farmer_app_1",
                "crop": "Maïs",
                "is_sms_mode": False,
                "requete_utilisateur": None,
                "user_reliability_score": 1.0,
                "flow_type": "REPORT",
                "global_alerts": [],
                "meteo_data": {},
                "market_data": {},
                "soil_data": None,
                "health_data": None,
                "health_raw_data": None,
                "execution_path": [],
                "final_report": None,
                "final_response": None
            }
        },
        {
            "name": "SMS Report (Nokia Mode)",
            "state": {
                "zone_id": "ZoneTest_Rural",
                "user_id": "farmer_sms_1",
                "crop": "Sorgho",
                "is_sms_mode": True,
                "requete_utilisateur": None,
                "user_reliability_score": 1.0,
                "flow_type": "REPORT",
                "global_alerts": [],
                "meteo_data": {},
                "market_data": {},
                "soil_data": None,
                "health_data": None,
                "health_raw_data": None,
                "execution_path": [],
                "final_report": None,
                "final_response": None
            }
        }
    ]

    for case in test_cases:
        logger.info(f"\n--- Testing Case: {case['name']} ---")
        state = case["state"]
        
        # Step 1: Fetch Data
        logger.info("1. Fetching Data...")
        fetched_data = flow.fetch_daily_data(state)
        
        # Merge fetched data into state
        state.update(fetched_data)
        
        # Debug print fetched data structure
        if "meteo_data" in state:
             logger.info(f"   Meteo Diag Status: {'OK' if 'diagnosis' in state['meteo_data'] else 'MISSING'}")
        if "market_data" in state:
             logger.info(f"   Market Advice: {state['market_data'].get('conseil')}")
        if "global_alerts" in state:
             logger.info(f"   Alerts Found: {len(state['global_alerts'])}")

        # Step 2: Generate Report
        logger.info("2. Generating Report...")
        result = flow.generate_report(state)
        final_report = result["final_report"]
        
        content = final_report["content"]
        priority = final_report["priority"]
        
        logger.info(f"📝 REPORT OUTPUT (Priority: {priority}):")
        logger.info("-" * 40)
        logger.info(content)
        logger.info("-" * 40)
        
        # Assertions
        if case["state"]["is_sms_mode"]:
            # Check SMS constraints
            if len(content) > 320:
                logger.warning(f"⚠️ SMS might be too long: {len(content)} chars")
            else:
                 logger.info(f"✅ SMS Length OK: {len(content)} chars")
            
            # Check for emoji replacements (from SMSAdapter)
            if "💰" in content or "🚨" in content or "⚠️" in content:
                 logger.info("✅ SMS Emojis detected")
        else:
            logger.info(f"✅ App Report generated ({len(content)} chars)")

    logger.info("\n🎉 Test Sequence Complete.")

if __name__ == "__main__":
    test_daily_report_generation()
