from tools.weather_db_utils import get_weather_data

if __name__ == '__main__':
    # Test sans filtre
    print('--- Toutes les données météo ---')
    all_data = get_weather_data()
    for row in all_data[:10]:
        print(row)

    # Test avec filtre ville
    print('\n--- Données pour Boromo ---')
    boromo_data = get_weather_data(city='Boromo')
    for row in boromo_data:
        print(row)

    # Test avec filtre ville et mois
    print('\n--- Données pour Boromo, mois 1 ---')
    boromo_jan = get_weather_data(city='Boromo', month=1)
    for row in boromo_jan:
        print(row)
