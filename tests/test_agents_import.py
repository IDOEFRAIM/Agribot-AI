"""
Test rapide des imports et compilation des workflows
"""
import sys
import logging

logging.basicConfig(level=logging.WARNING)  # Réduire les logs pour test

print("="*60)
print("🔍 TEST DES IMPORTS ET GRAPHES LANGGRAPH")
print("="*60)

try:
    print("\n1️⃣  Test FormationCoach...")
    from backend.agents.formation import FormationCoach
    agent1 = FormationCoach()
    workflow1 = agent1.build()
    print("   ✅ FormationCoach OK")
except Exception as e:
    print(f"   ❌ FormationCoach FAILED: {e}")
    sys.exit(1)

try:
    print("\n2️⃣  Test ClimateSentinel...")
    from backend.agents.sentinelle import ClimateSentinel
    agent2 = ClimateSentinel()
    workflow2 = agent2.build()
    print("   ✅ ClimateSentinel OK")
except Exception as e:
    print(f"   ❌ ClimateSentinel FAILED: {e}")
    sys.exit(1)

try:
    print("\n3️⃣  Test PlantHealthDoctor...")
    from backend.agents.plant_doctor import PlantHealthDoctor
    agent3 = PlantHealthDoctor()
    workflow3 = agent3.build()
    print("   ✅ PlantHealthDoctor OK")
except Exception as e:
    print(f"   ❌ PlantHealthDoctor FAILED: {e}")
    sys.exit(1)

try:
    print("\n4️⃣  Test AgriSoilAgent...")
    from backend.agents.soil import AgriSoilAgent
    agent4 = AgriSoilAgent()
    workflow4 = agent4.build()
    print("   ✅ AgriSoilAgent OK")
except Exception as e:
    print(f"   ❌ AgriSoilAgent FAILED: {e}")
    sys.exit(1)

try:
    print("\n5️⃣  Test MarketCoach...")
    from backend.agents.market import MarketCoach
    agent5 = MarketCoach()
    workflow5 = agent5.build()
    print("   ✅ MarketCoach OK")
except Exception as e:
    print(f"   ❌ MarketCoach FAILED: {e}")
    sys.exit(1)

try:
    print("\n6️⃣  Test MessageResponseFlow (Orchestrator)...")
    from backend.orchestrator.message_flow import MessageResponseFlow
    orchestrator = MessageResponseFlow()
    print("   ✅ MessageResponseFlow OK")
except Exception as e:
    print(f"   ❌ MessageResponseFlow FAILED: {e}")
    sys.exit(1)

print("\n" + "="*60)
print("🎉 TOUS LES TESTS RÉUSSIS!")
print("="*60)
print("\nLe serveur peut maintenant démarrer sans erreur 'unknown node'.")
