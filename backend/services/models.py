"""
SQLAlchemy Models — Schéma de la mémoire AgriConnect.

SOURCE UNIQUE DE VÉRITÉ pour le schéma ORM.
Utilisé par backend/services/db_handler.py (AgriDatabase)
et backend/core/database.py (engine centralisé).
"""

from sqlalchemy import (
    Column, String, DateTime, Boolean, Integer, Float,
    JSON, ForeignKey, Text,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Zone(Base):
    __tablename__ = "zones"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    region = Column(String, nullable=False)
    coordinates = Column(JSON)
    agro_type = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "region": self.region,
            "agro_type": self.agro_type,
        }


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True)
    phone = Column(String, unique=True, nullable=False)
    name = Column(String)
    language = Column(String, default="fr")
    zone_id = Column(String, ForeignKey("zones.id"))
    is_onboarded = Column(Boolean, default=False)
    voice_preference = Column(String, default="fr-FR-HenriNeural")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "phone": self.phone,
            "name": self.name,
            "zone_id": self.zone_id,
            "language": self.language,
            "is_onboarded": self.is_onboarded,
            "voice_preference": self.voice_preference,
        }


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(String, primary_key=True)
    type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    title = Column(String, default="")
    message = Column(Text, nullable=False)
    zone_id = Column(String, ForeignKey("zones.id"))
    target_crops = Column(JSON)
    processed = Column(Boolean, default=False)
    broadcast_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True))

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "severity": self.severity,
            "message": self.message,
            "zone_id": self.zone_id,
            "processed": self.processed,
        }


class MarketItem(Base):
    __tablename__ = "market_items"

    id = Column(String, primary_key=True)
    product_name = Column(String, nullable=False)
    price_kg = Column(Float, nullable=False)
    currency = Column(String, default="XOF")
    zone_id = Column(String, ForeignKey("zones.id"))
    market_name = Column(String)
    source = Column(String)
    date = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "product_name": self.product_name,
            "price_kg": self.price_kg,
            "currency": self.currency,
            "zone_id": self.zone_id,
            "market_name": self.market_name,
            "date": self.date.isoformat() if self.date else None,
        }


class WeatherData(Base):
    __tablename__ = "weather_data"

    id = Column(String, primary_key=True)
    zone_id = Column(String, ForeignKey("zones.id"))
    temperature = Column(Float)
    precipitation = Column(Float)
    humidity = Column(Float)
    wind_speed = Column(Float)
    forecast_date = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "zone_id": self.zone_id,
            "temperature": self.temperature,
            "precipitation": self.precipitation,
            "humidity": self.humidity,
        }


class Conversation(Base):
    """Historique des échanges pour mémoire conversationnelle."""
    __tablename__ = "conversations"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))
    channel = Column(String, default="api")          # api | whatsapp | sms
    status = Column(String, default="ACTIVE")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey("conversations.id", ondelete="CASCADE"))
    role = Column(String, nullable=False)             # user | assistant
    content = Column(Text, nullable=False)
    audio_url = Column(String)                        # chemin du fichier audio généré
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ── Tables proactives (actions utilisateur via agents) ────────

class UserCrop(Base):
    """Cultures enregistrées par l'utilisateur (via FormationCoach ou onboarding)."""
    __tablename__ = "user_crops"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))
    crop_name = Column(String, nullable=False)
    surface_ha = Column(Float)
    planting_date = Column(DateTime(timezone=True))
    expected_harvest = Column(DateTime(timezone=True))
    status = Column(String, default="ACTIVE")  # ACTIVE | HARVESTED | LOST
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id, "user_id": self.user_id,
            "crop_name": self.crop_name, "surface_ha": self.surface_ha,
            "status": self.status,
        }


class SurplusOffer(Base):
    """Offres de vente/surplus enregistrées par MarketCoach."""
    __tablename__ = "surplus_offers"

    id = Column(String, primary_key=True)
    user_id = Column(String, default="anonymous")
    product_name = Column(String, nullable=False)
    quantity_kg = Column(Float, nullable=False)
    price_kg = Column(Float)
    zone_id = Column(String, ForeignKey("zones.id"))
    location = Column(String)
    status = Column(String, default="OPEN")  # OPEN | MATCHED | SOLD | EXPIRED
    channel = Column(String, default="api")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id, "user_id": self.user_id,
            "product_name": self.product_name, "quantity_kg": self.quantity_kg,
            "price_kg": self.price_kg, "zone_id": self.zone_id,
            "location": self.location, "status": self.status,
        }


class SoilDiagnosis(Base):
    """Diagnostics de sol enregistrés par AgriSoilAgent."""
    __tablename__ = "soil_diagnoses"

    id = Column(String, primary_key=True)
    user_id = Column(String, default="anonymous")
    zone_id = Column(String, ForeignKey("zones.id"))
    village = Column(String)
    soil_type = Column(String)
    fertility = Column(String)
    ph_alert = Column(String)
    water_strategy = Column(String)
    adapted_crops = Column(JSON)
    raw_diagnosis = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id, "village": self.village,
            "soil_type": self.soil_type, "fertility": self.fertility,
            "adapted_crops": self.adapted_crops,
        }


class PlantDiagnosis(Base):
    """Diagnostics phytosanitaires enregistrés par PlantHealthDoctor."""
    __tablename__ = "plant_diagnoses"

    id = Column(String, primary_key=True)
    user_id = Column(String, default="anonymous")
    crop_name = Column(String)
    disease_name = Column(String)
    severity = Column(String)
    treatment_bio = Column(Text)
    treatment_chimique = Column(Text)
    estimated_cost = Column(Float)
    raw_diagnosis = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id, "crop_name": self.crop_name,
            "disease_name": self.disease_name, "severity": self.severity,
        }


class Reminder(Base):
    """Rappels planifiés pour les utilisateurs."""
    __tablename__ = "reminders"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"))
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    sent = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id, "title": self.title,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "sent": self.sent,
        }
