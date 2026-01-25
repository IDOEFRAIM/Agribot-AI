

import psycopg2
from typing import Optional, List, Dict

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'dbname': 'agri_weather',
    'user': 'agri_user',
    'password': 'agri_pass'
}

def get_weather_data(city: Optional[str] = None, month: Optional[int] = None) -> List[Dict]:
    """
    Récupère les données météo depuis PostgreSQL.
    :param city: nom de la ville (optionnel)
    :param month: mois (1-12, optionnel)
    :return: liste de dictionnaires avec les données météo
    """
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    query = "SELECT city, month, t_min, t_max, precip FROM weather_data"
    params = []
    conditions = []
    if city:
        conditions.append("city = %s")
        params.append(city)
    if month:
        conditions.append("month = %s")
        params.append(month)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY city, month"
    cur.execute(query, params)
    results = [
        {'city': row[0], 'month': row[1], 't_min': row[2], 't_max': row[3], 'precip': row[4]}
        for row in cur.fetchall()
    ]
    cur.close()
    conn.close()
    return results


def get_unique_weather_data(city: Optional[str] = None, month: Optional[int] = None) -> Optional[Dict]:
    """
    Retourne une seule entrée météo (la première trouvée) pour la ville et le mois donnés.
    :param city: nom de la ville (optionnel)
    :param month: mois (1-12, optionnel)
    :return: dictionnaire météo ou None
    """
    results = get_weather_data(city=city, month=month)
    if results:
        return results[0]
    return None