
import logging
from backend.orchestrator.message_flow import MessageResponseFlow

# Setup logging
logging.basicConfig(level=logging.INFO)

# Mock State that forces the inputs for the fusion
state = {
    "requete_utilisateur": "Y a-t-il un risque alimentaire presentement au burkina ?",
    "zone_id": "Bobo-Dioulasso",
    "crop": "Maïs",
    "needs": {
        "needs_sentinelle": True,
        "needs_formation": True, 
        "needs_market": True
    }
}

print("--- DIRECT TEST OF PROVEN COUNCIL FUSION ---")
bot = MessageResponseFlow()

# We call the method directly to bypass the router
# The method itself will call the sub-agents, so it might take 10-20s.
res = bot.execute_council_session(state)

print("\nRÉPONSE FINALE OBTENUE :\n")
print(res["final_response"])
