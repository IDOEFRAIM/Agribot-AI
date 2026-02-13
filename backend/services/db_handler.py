import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
import logging

from .models import (
    Base, User, Zone, Alert, MarketItem, WeatherData,
    Conversation, ConversationMessage,
    UserCrop, SurplusOffer, SoilDiagnosis, PlantDiagnosis, Reminder,
)

logger = logging.getLogger(__name__)

class AgriDatabase:
    """
    Abstraction de la couche mémoire (PostgreSQL).
    Gère les connexions, les sessions et les opérations métier pour l'Agent.

    Accepte soit une URL de DB (crée son propre engine),
    soit un engine/session_factory existant (réutilise celui de core/database.py).
    """

    def __init__(self, db_url: str = "", engine=None, session_factory=None):
        if engine and session_factory:
            # Réutilise l'engine centralisé de core/database.py
            self.engine = engine
            self.SessionLocal = session_factory
        elif db_url:
            self.engine = create_engine(
                db_url,
                pool_size=10,
                max_overflow=20,
                pool_pre_ping=True,
            )
            self.SessionLocal = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=self.engine,
            )
        else:
            raise ValueError("DATABASE_URL ou engine+session_factory requis.")

    @contextmanager
    def _get_session(self):
        """Fournit une session transactionnelle sécurisée."""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    # --- LOGIQUE UTILISATEURS ---
    
    def get_user_by_phone(self, phone: str) -> Optional[Dict[str, Any]]:
        with self._get_session() as session:
            user = session.query(User).filter(User.phone == phone).first()
            if user is None:
                return None
            return {"id": user.id, "phone": user.phone, "name": user.name,
                    "zone_id": user.zone_id, "language": user.language,
                    "is_onboarded": user.is_onboarded}

    def onboard_user(self, phone: str, name: str, zone_id: str, lang: str = "fr") -> Dict[str, Any]:
        with self._get_session() as session:
            user_id = str(uuid.uuid4())
            user = User(
                id=user_id,
                phone=phone,
                name=name,
                zone_id=zone_id,
                language=lang,
                is_onboarded=True
            )
            session.add(user)
            return {"id": user_id, "phone": phone, "name": name,
                    "zone_id": zone_id, "language": lang}

    # --- LOGIQUE ALERTES (Sentinelle) ---

    def create_alert(self, alert_type: str, severity: str, message: str, zone_id: str) -> Dict[str, Any]:
        with self._get_session() as session:
            alert_id = str(uuid.uuid4())
            alert = Alert(
                id=alert_id,
                type=alert_type,
                severity=severity,
                message=message,
                zone_id=zone_id,
                processed=False
            )
            session.add(alert)
            return {"id": alert_id, "type": alert_type, "severity": severity,
                    "message": message, "zone_id": zone_id}

    def get_pending_alerts(self, zone_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._get_session() as session:
            query = session.query(Alert).filter(Alert.processed == False)
            if zone_id:
                query = query.filter(Alert.zone_id == zone_id)
            alerts = query.all()
            return [{"id": a.id, "type": a.type, "severity": a.severity,
                      "message": a.message, "zone_id": a.zone_id} for a in alerts]

    # --- LOGIQUE MARCHÉ (MarketCoach) ---

    def get_latest_market_prices(self, product: str, zone_id: str, limit: int = 5) -> List[Dict[str, Any]]:
        with self._get_session() as session:
            # Parameterized LIKE to prevent SQL wildcard injection
            items = session.query(MarketItem).filter(
                MarketItem.product_name.ilike(f"%{product}%"),
                MarketItem.zone_id == zone_id
            ).order_by(MarketItem.date.desc()).limit(limit).all()
            return [{"product_name": m.product_name, "zone_id": m.zone_id,
                      "price": m.price_kg, "date": str(m.date)} for m in items]

    # --- SANTÉ DU SYSTÈME ---

    def check_connection(self) -> bool:
        """Vérifie si la DB répond."""
        try:
            with self._get_session() as session:
                session.execute(text("SELECT 1"))
                return True
        except Exception:
            return False

    # --- MÉTÉO (WeatherData) ---

    def save_weather(self, zone_id: str, temperature: float = None,
                     precipitation: float = None, humidity: float = None,
                     forecast_date: str = None) -> Dict[str, Any]:
        with self._get_session() as session:
            weather_id = str(uuid.uuid4())
            weather = WeatherData(
                id=weather_id,
                zone_id=zone_id,
                temperature=temperature,
                precipitation=precipitation,
                humidity=humidity,
                forecast_date=forecast_date or datetime.utcnow(),
            )
            session.add(weather)
            return {"id": weather_id, "zone_id": zone_id,
                    "temperature": temperature, "precipitation": precipitation}

    # --- CONVERSATIONS (mémoire) ---

    def log_conversation(self, user_id: str, user_message: str,
                         assistant_message: str, audio_url: str = None,
                         channel: str = "api") -> str:
        """
        Sauvegarde un échange complet (question + réponse).
        Retourne le conversation_id.
        """
        with self._get_session() as session:
            conv_id = str(uuid.uuid4())
            conv = Conversation(id=conv_id, user_id=user_id, channel=channel)
            session.add(conv)
            session.flush()

            # Message utilisateur
            session.add(ConversationMessage(
                id=str(uuid.uuid4()),
                conversation_id=conv_id,
                role="user",
                content=user_message or "",
            ))
            # Réponse assistant
            session.add(ConversationMessage(
                id=str(uuid.uuid4()),
                conversation_id=conv_id,
                role="assistant",
                content=assistant_message or "Informations indisponibles",
                audio_url=audio_url,
            ))
            return conv_id

    # ── PROACTIVE : Surplus / Marché (MarketCoach) ────────────────

    def save_surplus_offer(
        self, product_name: str, quantity_kg: float,
        price_kg: float = None, zone_id: str = None,
        location: str = None, user_id: str = "anonymous",
        channel: str = "api",
    ) -> Dict[str, Any]:
        """Enregistre une offre de surplus détectée par MarketCoach."""
        with self._get_session() as session:
            offer_id = str(uuid.uuid4())
            offer = SurplusOffer(
                id=offer_id,
                user_id=user_id,
                product_name=product_name,
                quantity_kg=quantity_kg,
                price_kg=price_kg,
                zone_id=zone_id,
                location=location,
                channel=channel,
            )
            session.add(offer)
            logger.info("💰 Surplus offer saved: %s kg of %s", quantity_kg, product_name)
            return offer.to_dict()

    def get_open_surplus_offers(
        self, product: str = None, zone_id: str = None, limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """Récupère les offres de surplus ouvertes (matching acheteur/vendeur)."""
        with self._get_session() as session:
            query = session.query(SurplusOffer).filter(SurplusOffer.status == "OPEN")
            if product:
                query = query.filter(SurplusOffer.product_name.ilike(f"%{product}%"))
            if zone_id:
                query = query.filter(SurplusOffer.zone_id == zone_id)
            offers = query.order_by(SurplusOffer.created_at.desc()).limit(limit).all()
            return [o.to_dict() for o in offers]

    # ── PROACTIVE : Diagnostic Sol (AgriSoilAgent) ────────────────

    def save_soil_diagnosis(
        self, village: str, diagnosis: Dict[str, Any],
        zone_id: str = None, user_id: str = "anonymous",
    ) -> Dict[str, Any]:
        """Persiste un diagnostic sol produit par AgriSoilAgent."""
        identite = diagnosis.get("identite_pedologique", {})
        sante = diagnosis.get("bilan_sante", {})
        eau = diagnosis.get("gestion_eau", {})

        with self._get_session() as session:
            diag_id = str(uuid.uuid4())
            entry = SoilDiagnosis(
                id=diag_id,
                user_id=user_id,
                zone_id=zone_id,
                village=village,
                soil_type=identite.get("nom_local"),
                fertility=sante.get("fertilite"),
                ph_alert=sante.get("alerte_ph"),
                water_strategy=eau.get("strategie"),
                adapted_crops=identite.get("cultures_adaptees"),
                raw_diagnosis=diagnosis,
            )
            session.add(entry)
            logger.info("🌍 Soil diagnosis saved: %s (%s)", village, diag_id)
            return entry.to_dict()

    # ── PROACTIVE : Diagnostic Plante (PlantHealthDoctor) ─────────

    def save_plant_diagnosis(
        self, crop_name: str, diagnosis: Dict[str, Any],
        user_id: str = "anonymous",
    ) -> Dict[str, Any]:
        """Persiste un diagnostic phytosanitaire par PlantHealthDoctor."""
        with self._get_session() as session:
            diag_id = str(uuid.uuid4())
            entry = PlantDiagnosis(
                id=diag_id,
                user_id=user_id,
                crop_name=crop_name,
                disease_name=diagnosis.get("disease_name"),
                severity=diagnosis.get("severity"),
                treatment_bio=diagnosis.get("treatment_bio"),
                treatment_chimique=diagnosis.get("treatment_chimique"),
                estimated_cost=diagnosis.get("estimated_cost"),
                raw_diagnosis=diagnosis,
            )
            session.add(entry)
            logger.info("🌱 Plant diagnosis saved: %s (%s)", crop_name, diag_id)
            return entry.to_dict()

    # ── PROACTIVE : Cultures utilisateur (onboarding) ─────────────

    def register_user_crop(
        self, user_id: str, crop_name: str,
        surface_ha: float = None, planting_date=None,
    ) -> Dict[str, Any]:
        """Enregistre une culture déclarée par l'utilisateur."""
        with self._get_session() as session:
            crop_id = str(uuid.uuid4())
            crop = UserCrop(
                id=crop_id,
                user_id=user_id,
                crop_name=crop_name,
                surface_ha=surface_ha,
                planting_date=planting_date,
            )
            session.add(crop)
            logger.info("🌾 User crop registered: %s for %s", crop_name, user_id)
            return crop.to_dict()

    # ── PROACTIVE : Rappels ────────────────────────────────────────

    def create_reminder(
        self, user_id: str, title: str, message: str, scheduled_at,
    ) -> Dict[str, Any]:
        """Planifie un rappel pour l'utilisateur."""
        with self._get_session() as session:
            reminder_id = str(uuid.uuid4())
            reminder = Reminder(
                id=reminder_id,
                user_id=user_id,
                title=title,
                message=message,
                scheduled_at=scheduled_at,
            )
            session.add(reminder)
            logger.info("⏰ Reminder created: %s for %s", title, user_id)
            return reminder.to_dict()