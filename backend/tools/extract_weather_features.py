import json
import sys

# Usage: python tools/extract_weather_features.py <city>
# Default city: Bobo Dioulasso

def extract_features(city_name):
    with open('data/weather_service_latest.json', encoding='utf-8') as f:
        data = json.load(f)
    for entry in data.get('results', []):
        # Nouveau format : full_data est une string JSON
        try:
            full_data = json.loads(entry.get('full_data', '{}'))
        except Exception:
            continue
        city = full_data.get('city', '').lower()
        if city_name.lower() in city:
            t_min = full_data.get('t_min')
            t_max = full_data.get('t_max')
            precip = full_data.get('precip')
            print(f"City: {city_name}")
            print(f"t_min: {t_min}")
            print(f"t_max: {t_max}")
            print(f"precip: {precip}")
            return
    print(f"City '{city_name}' not found in weather_service_latest.json")

if __name__ == "__main__":
    # Liste des villes à tester
    cities = [
        "Bobo Dioulasso",
        "Boromo",
        "Dédougou",
        "Dori",
        "Fada N'Gourma",
        "Gaoua",
        "Ouahigouya",
        "Pô"
    ]
    if len(sys.argv) > 1:
        # Si une ville est passée en argument, ne tester que celle-ci
        extract_features(sys.argv[1])
    else:
        for city in cities:
            extract_features(city)
            print("-"*40)
