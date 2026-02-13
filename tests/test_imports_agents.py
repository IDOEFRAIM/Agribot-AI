"""
Test rapide pour vérifier que les agents se chargent correctement
"""

def test_imports():
    """Test des imports basiques"""
    try:
        print("Test 1: Import formation...")
        from backend.agents.formation import FormationCoach
        print("✅ FormationCoach OK")
        
        print("Test 2: Import sentinelle...")
        from backend.agents.sentinelle import ClimateSentinel
        print("✅ ClimateSentinel OK")
        
        print("Test 3: Import plant_doctor...")
        from backend.agents.plant_doctor import PlantHealthDoctor
        print("✅ PlantHealthDoctor OK")
        
        print("Test 4: Import market...")
        from backend.agents.market import MarketCoach
        print("✅ MarketCoach OK")
        
        print("Test 5: Import soil...")
        from backend.agents.soil import AgriSoilAgent
        print("✅ AgriSoilAgent OK")
        
        print("\n" + "="*60)
        print("✅ TOUS LES IMPORTS RÉUSSIS!")
        print("="*60)
        return True
        
    except Exception as e:
        print(f"\n❌ ERREUR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    test_imports()
