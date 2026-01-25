
import psycopg2
import json
from datetime import datetime

# --- CREATE TABLES IF NOT EXISTS ---
def create_tables(conn):
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS weather_data (
            id SERIAL PRIMARY KEY,
            city VARCHAR(100) NOT NULL,
            year INT,
            month INT NOT NULL,
            t_min REAL,
            t_max REAL,
            precip REAL,
            source_url TEXT
        );
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS weather_bulletins (
            id SERIAL PRIMARY KEY,
            title TEXT,
            bulletin_type VARCHAR(20),
            period_start DATE,
            period_end DATE,
            created_at TIMESTAMP,
            url TEXT,
            content TEXT,
            provider TEXT,
            priority VARCHAR(20),
            original_pdf TEXT
        );
    ''')
    conn.commit()
    cur.close()

# --- CONFIGURATION ---
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'dbname': 'agri_weather',
    'user': 'agri_user',
    'password': 'agri_pass'
}

# --- INSERT WEATHER DATA ---
def insert_weather_data(conn, weather_json_path):
    with open(weather_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    cur = conn.cursor()
    for entry in data['results']:
        city = entry['city']
        # full_data is a JSON string
        full_data = json.loads(entry['full_data'])
        t_min = full_data['t_min']
        t_max = full_data['t_max']
        precip = full_data['precip']
        source_url = full_data.get('source_url')
        n_months = min(len(t_min), len(t_max), len(precip))
        for month in range(1, n_months + 1):
            tmin_val = t_min[month-1] if month-1 < len(t_min) else None
            tmax_val = t_max[month-1] if month-1 < len(t_max) else None
            precip_val = precip[month-1] if month-1 < len(precip) else None
            cur.execute(
                """
                INSERT INTO weather_data (city, month, t_min, t_max, precip, source_url)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (city, month, tmin_val, tmax_val, precip_val, source_url)
            )
    conn.commit()
    cur.close()

# --- INSERT BULLETINS ---
def insert_bulletins(conn, bulletins_json_path):
    with open(bulletins_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    cur = conn.cursor()
    for entry in data['results']:
        title = entry.get('title')
        url = entry.get('url')
        content = entry.get('content')
        created_at = entry.get('created_at')
        provider = entry.get('metadata', {}).get('provider')
        priority = entry.get('metadata', {}).get('priority')
        original_pdf = entry.get('metadata', {}).get('original_pdf')
        # Type et période à extraire selon la structure réelle (à adapter si besoin)
        bulletin_type = None
        period_start = None
        period_end = None
        if title:
            if 'journalier' in title.lower():
                bulletin_type = 'journalier'
            elif 'hebdo' in title.lower():
                bulletin_type = 'hebdomadaire'
            elif 'mensuel' in title.lower():
                bulletin_type = 'mensuel'
            elif 'décadaire' in title.lower():
                bulletin_type = 'decadaire'
            else:
                bulletin_type = 'autre'
        # Dates à parser si possible
        try:
            if created_at:
                created_at = datetime.fromisoformat(created_at)
        except Exception:
            created_at = None
        cur.execute(
            """
            INSERT INTO weather_bulletins (title, bulletin_type, period_start, period_end, created_at, url, content, provider, priority, original_pdf)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (title, bulletin_type, period_start, period_end, created_at, url, content, provider, priority, original_pdf)
        )
    conn.commit()
    cur.close()


if __name__ == '__main__':
    conn = psycopg2.connect(**DB_CONFIG)
    create_tables(conn)
    # Adapter les chemins selon l'organisation réelle
    insert_weather_data(conn, 'data/weather_service_latest.json')
    insert_bulletins(conn, 'data/meteo_burkina_latest.json')
    conn.close()
