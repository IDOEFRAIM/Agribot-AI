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


# ══════════════════════════════════════════════════════════════
# AGRIBUSINESS — Modèles marketplace (alignés sur le Prisma frontend)
# ══════════════════════════════════════════════════════════════

class ClimaticRegion(Base):
    """Régions climatiques du Burkina Faso."""
    __tablename__ = "climatic_regions"

    id = Column(String, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {"id": self.id, "name": self.name, "description": self.description}


class Producer(Base):
    """Producteur/agriculteur inscrit sur la plateforme."""
    __tablename__ = "producers"

    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    business_name = Column(String)
    status = Column(String, default="ACTIVE")      # PENDING | ACTIVE | SUSPENDED
    zone_id = Column(String, ForeignKey("zones.id"))
    region = Column(String)
    province = Column(String)
    commune = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id, "user_id": self.user_id,
            "business_name": self.business_name, "status": self.status,
            "zone_id": self.zone_id, "commune": self.commune,
        }


class Farm(Base):
    """Exploitation agricole d'un producteur."""
    __tablename__ = "farms"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    location = Column(String)
    size = Column(Float)                 # hectares
    soil_type = Column(String)
    water_source = Column(String)
    zone_id = Column(String, ForeignKey("zones.id"))
    producer_id = Column(String, ForeignKey("producers.id", ondelete="CASCADE"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "location": self.location,
            "size": self.size, "soil_type": self.soil_type,
            "producer_id": self.producer_id, "zone_id": self.zone_id,
        }


class Stock(Base):
    """Inventaire d'une exploitation (intrants, récoltes, équipement)."""
    __tablename__ = "stocks"

    id = Column(String, primary_key=True)
    farm_id = Column(String, ForeignKey("farms.id", ondelete="CASCADE"))
    item_name = Column(String, nullable=False)
    quantity = Column(Float, default=0)
    unit = Column(String, default="kg")
    type = Column(String, default="HARVEST")   # INPUT | HARVEST | EQUIPMENT
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id, "farm_id": self.farm_id,
            "item_name": self.item_name, "quantity": self.quantity,
            "unit": self.unit, "type": self.type,
        }


class StockMovement(Base):
    """Mouvements d'inventaire (entrées, sorties, pertes)."""
    __tablename__ = "stock_movements"

    id = Column(String, primary_key=True)
    stock_id = Column(String, ForeignKey("stocks.id", ondelete="CASCADE"))
    type = Column(String, nullable=False)    # IN | OUT | WASTE
    quantity = Column(Float, nullable=False)
    reason = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id, "stock_id": self.stock_id,
            "type": self.type, "quantity": self.quantity, "reason": self.reason,
        }


class Expense(Base):
    """Dépenses associées à une exploitation."""
    __tablename__ = "expenses"

    id = Column(String, primary_key=True)
    farm_id = Column(String, ForeignKey("farms.id", ondelete="CASCADE"))
    label = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String, default="OTHER")   # LABOUR | FUEL | SEEDS | FERTILIZER | TRANSPORT | OTHER
    date = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id, "farm_id": self.farm_id,
            "label": self.label, "amount": self.amount,
            "category": self.category,
        }


class Product(Base):
    """Produit mis en vente par un producteur (catalogue public)."""
    __tablename__ = "products"

    id = Column(String, primary_key=True)
    short_code = Column(String, unique=True)
    name = Column(String, nullable=False, default="Produit")
    category_label = Column(String)
    local_names = Column(JSON)             # {"moore": "...", "dioula": "..."}
    description = Column(Text)
    price = Column(Float, nullable=False)
    unit = Column(String, default="kg")
    quantity_for_sale = Column(Float, default=0)
    images = Column(JSON, default=list)
    audio_url = Column(String)
    producer_id = Column(String, ForeignKey("producers.id", ondelete="CASCADE"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id, "short_code": self.short_code,
            "name": self.name, "category_label": self.category_label,
            "price": self.price, "unit": self.unit,
            "quantity_for_sale": self.quantity_for_sale,
            "producer_id": self.producer_id,
        }


class Order(Base):
    """Commande passée par un acheteur."""
    __tablename__ = "orders"

    id = Column(String, primary_key=True)
    buyer_id = Column(String, ForeignKey("users.id"))
    customer_name = Column(String)
    customer_phone = Column(String)
    zone_id = Column(String, ForeignKey("zones.id"))
    payment_method = Column(String, default="CASH")   # CASH | MOBILE_MONEY | BANK_TRANSFER
    city = Column(String)
    gps_lat = Column(Float)
    gps_lng = Column(Float)
    delivery_desc = Column(String)
    audio_url = Column(String)
    status = Column(String, default="PENDING")         # PENDING | CONFIRMED | SHIPPED | DELIVERED | CANCELLED
    source = Column(String, default="WHATSAPP")        # APP | WHATSAPP | VOICE_CALL
    total_amount = Column(Float, default=0)
    whatsapp_id = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def to_dict(self):
        return {
            "id": self.id, "buyer_id": self.buyer_id,
            "customer_name": self.customer_name, "customer_phone": self.customer_phone,
            "status": self.status, "total_amount": self.total_amount,
            "zone_id": self.zone_id, "source": self.source,
        }


class OrderItem(Base):
    """Lignes de commande (produits commandés)."""
    __tablename__ = "order_items"

    id = Column(String, primary_key=True)
    order_id = Column(String, ForeignKey("orders.id", ondelete="CASCADE"))
    product_id = Column(String, ForeignKey("products.id"))
    quantity = Column(Float, nullable=False)
    price_at_sale = Column(Float, nullable=False)

    def to_dict(self):
        return {
            "id": self.id, "order_id": self.order_id,
            "product_id": self.product_id, "quantity": self.quantity,
            "price_at_sale": self.price_at_sale,
        }


class MarketAlert(Base):
    """Alertes de marché pour le matching acheteur ↔ vendeur."""
    __tablename__ = "market_alerts"

    id = Column(String, primary_key=True)
    product_name = Column(String, nullable=False)
    zone_id = Column(String, ForeignKey("zones.id"))
    buyer_phone = Column(String)
    status = Column(String, default="SEARCHING")   # SEARCHING | MATCHED | COMPLETED
    matched_product_id = Column(String)
    matched_producer_phone = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self):
        return {
            "id": self.id, "product_name": self.product_name,
            "zone_id": self.zone_id, "buyer_phone": self.buyer_phone,
            "status": self.status,
        }


# ══════════════════════════════════════════════════════════════
# MÉMOIRE 3 NIVEAUX — Modèles importés
# ══════════════════════════════════════════════════════════════
# Les modèles UserFarmProfileModel et EpisodicMemoryModel sont
# définis dans backend/services/memory/ et importés ici pour
# que SQLAlchemy les découvre via Base.metadata.
from backend.services.memory.user_profile import UserFarmProfileModel
from backend.services.memory.episodic_memory import EpisodicMemoryModel
