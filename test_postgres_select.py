import psycopg2

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'dbname': 'agri_weather',
    'user': 'agri_user',
    'password': 'agri_pass'
}

def test_weather_data():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    print('--- Weather Data Sample ---')
    cur.execute("""
        SELECT city, month, t_min, t_max, precip
        FROM weather_data
        ORDER BY city, month
        LIMIT 10;
    """)
    for row in cur.fetchall():
        print(row)
    cur.close()
    conn.close()

def test_bulletins():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    print('--- Bulletins Sample ---')
    cur.execute("""
        SELECT title, bulletin_type, created_at
        FROM weather_bulletins
        ORDER BY created_at DESC
        LIMIT 5;
    """)
    for row in cur.fetchall():
        print(row)
    cur.close()
    conn.close()

if __name__ == '__main__':
    test_weather_data()
    test_bulletins()
