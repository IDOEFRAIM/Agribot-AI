"""
SQLAlchemy Models - Remplace Prisma Schema
"""

from sqlalchemy import Column, String, DateTime, Boolean, Integer, Float, JSON, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()

class Zone(Base):
    __tablename__ = 'zones'
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    region = Column(String, nullable=False)
    coordinates = Column(JSON)
    agro_type = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "region": self.region,
            "coordinates": self.coordinates,
            "agro_type": self.agro_type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class User(Base):
    __tablename__ = 'users'
    
    id = Column(String, primary_key=True)
    phone = Column(String, unique=True, nullable=False)
    name = Column(String)
    language = Column(String, default='fr')
    zone_id = Column(String, ForeignKey('zones.id'))
    is_onboarded = Column(Boolean, default=False)
    voice_preference = Column(String, default='azure_neural')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def to_dict(self):
        return {
            "id": self.id,
            "phone": self.phone,
            "name": self.name,
            "language": self.language,
            "zone_id": self.zone_id,
            "is_onboarded": self.is_onboarded,
            "voice_preference": self.voice_preference,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class UserCrop(Base):
    __tablename__ = 'user_crops'
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'))
    crop_name = Column(String, nullable=False)
    surface_ha = Column(Float)
    planting_date = Column(DateTime(timezone=True))
    expected_harvest = Column(DateTime(timezone=True))
    status = Column(String, default='ACTIVE')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "crop_name": self.crop_name,
            "surface_ha": self.surface_ha,
            "planting_date": self.planting_date.isoformat() if self.planting_date else None,
            "expected_harvest": self.expected_harvest.isoformat() if self.expected_harvest else None,
            "status": self.status
        }


class Alert(Base):
    __tablename__ = 'alerts'
    
    id = Column(String, primary_key=True)
    type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    zone_id = Column(String, ForeignKey('zones.id'))
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
            "title": self.title,
            "message": self.message,
            "zone_id": self.zone_id,
            "target_crops": self.target_crops,
            "processed": self.processed,
            "broadcast_count": self.broadcast_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None
        }


class MarketItem(Base):
    __tablename__ = 'market_items'
    
    id = Column(String, primary_key=True)
    product_name = Column(String, nullable=False)
    price_kg = Column(Float, nullable=False)
    currency = Column(String, default='XOF')
    zone_id = Column(String, ForeignKey('zones.id'))
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
            "source": self.source,
            "date": self.date.isoformat() if self.date else None
        }


class WeatherData(Base):
    __tablename__ = 'weather_data'
    
    id = Column(String, primary_key=True)
    zone_id = Column(String, ForeignKey('zones.id'))
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
            "wind_speed": self.wind_speed,
            "forecast_date": self.forecast_date.isoformat() if self.forecast_date else None
        }


class Conversation(Base):
    __tablename__ = 'conversations'
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'))
    channel = Column(String, default='whatsapp')
    status = Column(String, default='ACTIVE')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "channel": self.channel,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class ConversationMessage(Base):
    __tablename__ = 'conversation_messages'
    
    id = Column(String, primary_key=True)
    conversation_id = Column(String, ForeignKey('conversations.id', ondelete='CASCADE'))
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    audio_url = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "audio_url": self.audio_url,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class Reminder(Base):
    __tablename__ = 'reminders'
    
    id = Column(String, primary_key=True)
    user_id = Column(String, ForeignKey('users.id', ondelete='CASCADE'))
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    scheduled_at = Column(DateTime(timezone=True), nullable=False)
    sent = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "message": self.message,
            "scheduled_at": self.scheduled_at.isoformat() if self.scheduled_at else None,
            "sent": self.sent
        }
