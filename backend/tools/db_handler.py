import psycopg2
import logging
import os
import json
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger("DBHandler")

class DBHandler:
    """
    Gestionnaire de base de données PostgreSQL pour AgriBot.
    Gère les connexions et les opérations CRUD spécifiques (Offres, Stocks, Utilisateurs).
    """

    def __init__(self, db_config: Optional[Dict[str, str]] = None):
        if db_config:
            self.config = db_config
        else:
            # Valeurs par défaut alignées avec docker-compose.yml
            self.config = {
                "dbname": os.getenv("POSTGRES_DB", "agri_weather"),
                "user": os.getenv("POSTGRES_USER", "agri_user"),
                "password": os.getenv("POSTGRES_PASSWORD", "agri_pass"),
                "host": os.getenv("POSTGRES_HOST", "localhost"),
                "port": os.getenv("POSTGRES_PORT", "5433")
            }
        
        self.conn = None
        # On tente l'initialisation des tables mais on n'échoue pas si pas de DB
        self._ensure_tables_exist()

    def get_connection(self):
        """Établit ou récupère une connexion active."""
        try:
            if self.conn is None or self.conn.closed:
                self.conn = psycopg2.connect(**self.config)
            return self.conn
        except Exception as e:
            # logger.warning(f"DB non connectée: {e}") 
            # On log en warning seulement pour ne pas spammer si pas de DB installée
            return None

    def _ensure_tables_exist(self):
        """Crée les tables nécessaires au démarrage."""
        create_surplus_table_sql = """
        CREATE TABLE IF NOT EXISTS surplus_stocks (
            id SERIAL PRIMARY KEY,
            commodity VARCHAR(50) NOT NULL,
            quantity FLOAT NOT NULL,
            unit VARCHAR(20) DEFAULT 'kg',
            location VARCHAR(100),
            contact VARCHAR(50),
            user_id VARCHAR(50),
            status VARCHAR(20) DEFAULT 'PENDING',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        
        create_logistics_table_sql = """
        CREATE TABLE IF NOT EXISTS logistics_centers (
            id SERIAL PRIMARY KEY,
            city VARCHAR(50) UNIQUE NOT NULL,
            address TEXT NOT NULL,
            type VARCHAR(20) DEFAULT 'SONAGESS'
        );
        """

        create_weather_table_sql = """
        CREATE TABLE IF NOT EXISTS weather_records (
            id SERIAL PRIMARY KEY,
            zone_name VARCHAR(100) NOT NULL,
            record_date DATE NOT NULL,
            latitude FLOAT,
            longitude FLOAT,
            temp_max FLOAT,
            temp_min FLOAT,
            precip_mm FLOAT,
            et0 FLOAT,
            source VARCHAR(50) DEFAULT 'OpenMeteo',
            raw_data JSONB,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(zone_name, record_date)
        );
        """

        # Données de référence SONAGESS
        initial_centers = [
            ("nouna", "Magasin SONAGESS, Secteur 4, Route de Dédougou"),
            ("dedougou", "Magasin Central, Face à la Gare Routière"),
            ("bobo", "Silos de la Zone Industrielle (Côté SOFIB)"),
            ("kaya", "Entrepôts Régionaux, Route de Dori"),
            ("ouaga", "Siège SONAGESS, Gounghin")
        ]

        try:
            conn = self.get_connection()
            if conn:
                with conn.cursor() as cur:
                    # 1. Création des tables
                    cur.execute(create_surplus_table_sql)
                    cur.execute(create_logistics_table_sql)
                    cur.execute(create_weather_table_sql)
                    
                    # 2. Seeding des centres si vide
                    cur.execute("SELECT COUNT(*) FROM logistics_centers")
                    count = cur.fetchone()[0]
                    if count == 0:
                        cur.executemany(
                            "INSERT INTO logistics_centers (city, address) VALUES (%s, %s)",
                            initial_centers
                        )
                        logger.info("Données logistiques SONAGESS initialisées en DB.")
                        
                conn.commit()
        except Exception as e:
            # logger.warning(f"DB setup warning: {e}")
            pass

    def save_weather_data(self, zone_name: str, lat: float, lon: float, daily_data: Dict[str, Any]):
        """
        Sauvegarde une série de données météo journalières en base.
        Effectue un UPSERT (Update on Conflict) pour éviter les doublons.
        """
        conn = self.get_connection()
        if not conn:
            return

        dates = daily_data.get("time", [])
        temp_max = daily_data.get("temperature_2m_max", [])
        temp_min = daily_data.get("temperature_2m_min", [])
        precip = daily_data.get("precipitation_sum", [])
        et0 = daily_data.get("et0_fao_evapotranspiration", [])
        
        # On suppose que toutes les listes ont la même longueur que dates
        upsert_sql = """
            INSERT INTO weather_records (
                zone_name, record_date, latitude, longitude, 
                temp_max, temp_min, precip_mm, et0, raw_data
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (zone_name, record_date) 
            DO UPDATE SET
                temp_max = EXCLUDED.temp_max,
                temp_min = EXCLUDED.temp_min,
                precip_mm = EXCLUDED.precip_mm,
                et0 = EXCLUDED.et0,
                updated_at = CURRENT_TIMESTAMP;
        """

        try:
            with conn.cursor() as cur:
                for i, date_str in enumerate(dates):
                    # Protection contre index out of range si données incomplètes
                    t_max = temp_max[i] if i < len(temp_max) else None
                    t_min = temp_min[i] if i < len(temp_min) else None
                    p_sum = precip[i] if i < len(precip) else None
                    e_fao = et0[i] if i < len(et0) else None
                    
                    # Petit JSON contextuel pour la colonne raw_data (optionnel)
                    daily_json = json.dumps({
                        "weathercode": daily_data.get("weathercode", [])[i] if "weathercode" in daily_data else None,
                        "precipitation_hours": daily_data.get("precipitation_hours", [])[i] if "precipitation_hours" in daily_data else None
                    })

                    cur.execute(upsert_sql, (
                        zone_name, date_str, lat, lon,
                        t_max, t_min, p_sum, e_fao, daily_json
                    ))
                conn.commit()
                logger.info("Météo %s sauvegardée en DB (%d jours).", zone_name, len(dates))
        except Exception as e:
            logger.error("Erreur insertion météo pour %s: %s", zone_name, e)
            conn.rollback()

    def get_logistics_center(self, location_text: str) -> Optional[str]:
        """Récupère l'adresse SONAGESS si la ville est détectée dans la localité."""
        # Recherche inversée : "Si la ville en DB est contenue dans l'input utilisateur"
        # Ex: User="Je suis à Bobo-Dioulasso" -> DB="bobo" -> Match
        sql = "SELECT address FROM logistics_centers WHERE %s ILIKE '%%' || city || '%%' LIMIT 1"
        try:
            conn = self.get_connection()
            if not conn: return None
            
            with conn.cursor() as cur:
                cur.execute(sql, (location_text,))
                res = cur.fetchone()
                if res:
                    return res[0]
            return None
        except Exception as e:
            logger.error("Erreur recherche logistique: %s", e)
            return None

    def register_surplus(self, commodity: str, quantity: float, location: str, contact: str = "N/A", user_id: str = "anonymous") -> bool:
        """Enregistre une offre de vente (surplus) dans la base."""
        sql = """
        INSERT INTO surplus_stocks (commodity, quantity, location, contact, user_id)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id;
        """
        try:
            conn = self.get_connection()
            if not conn:
                logger.warning("Pas de connexion DB pour sauvegarder le surplus.")
                return False
                
            with conn.cursor() as cur:
                cur.execute(sql, (commodity.lower(), quantity, location, contact, user_id))
                new_id = cur.fetchone()[0]
            conn.commit()
            logger.info("Surplus enregistré en DB : ID %s - %s", new_id, commodity)
            return True
        except Exception as e:
            logger.error("Erreur DB register_surplus : %s", e)
            if conn:
                conn.rollback()
            return False
