"""
Service Database - API REST pour PostgreSQL
Remplace Prisma avec SQLAlchemy pur Python
"""

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL manquante dans .env")

# SQLAlchemy Engine
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# FastAPI App
app = FastAPI(
    title="Agri-OS Database Service",
    description="Service CRUD pour PostgreSQL - Remplace Prisma",
    version="2.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency pour obtenir session DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ===========================
# HEALTH CHECK
# ===========================

@app.get("/health")
def health_check():
    """Vérifier que le service et PostgreSQL sont opérationnels"""
    try:
        db = SessionLocal()
        from sqlalchemy import text
        db.execute(text("SELECT 1"))
        db.close()
        return {
            "status": "healthy",
            "service": "database",
            "database": "connected"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "database",
            "error": str(e)
        }

# ===========================
# ZONES ENDPOINTS
# ===========================

@app.get("/zones")
def list_zones(db: Session = Depends(get_db)):
    """Liste toutes les zones agro-écologiques"""
    from models import Zone
    zones = db.query(Zone).all()
    return {"zones": [z.to_dict() for z in zones]}

@app.get("/zones/{zone_id}")
def get_zone(zone_id: str, db: Session = Depends(get_db)):
    """Récupérer une zone par ID"""
    from models import Zone
    zone = db.query(Zone).filter(Zone.id == zone_id).first()
    if not zone:
        raise HTTPException(status_code=404, detail="Zone non trouvée")
    return zone.to_dict()

# ===========================
# USERS ENDPOINTS
# ===========================

@app.post("/users")
def create_user(user_data: dict, db: Session = Depends(get_db)):
    """Créer un nouvel utilisateur"""
    from models import User
    import uuid
    
    user = User(
        id=str(uuid.uuid4()),
        phone=user_data["phone"],
        name=user_data.get("name"),
        language=user_data.get("language", "fr"),
        zone_id=user_data.get("zone_id"),
        is_onboarded=user_data.get("is_onboarded", False),
        voice_preference=user_data.get("voice_preference", "azure_neural")
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    return user.to_dict()

@app.get("/users/{phone}")
def get_user_by_phone(phone: str, db: Session = Depends(get_db)):
    """Récupérer utilisateur par téléphone"""
    from models import User
    user = db.query(User).filter(User.phone == phone).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return user.to_dict()

# ===========================
# ALERTS ENDPOINTS (Event-Driven Core)
# ===========================

@app.post("/alerts")
def create_alert(alert_data: dict, db: Session = Depends(get_db)):
    """Créer une nouvelle alerte"""
    from models import Alert
    import uuid
    from datetime import datetime
    
    alert = Alert(
        id=str(uuid.uuid4()),
        type=alert_data["type"],
        severity=alert_data["severity"],
        title=alert_data["title"],
        message=alert_data["message"],
        zone_id=alert_data.get("zone_id"),
        target_crops=alert_data.get("target_crops"),
        processed=False,
        broadcast_count=0,
        created_at=datetime.now()
    )
    
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert.to_dict()

@app.get("/alerts")
def list_alerts(processed: bool = None, zone_id: str = None, db: Session = Depends(get_db)):
    """Liste alertes avec filtres optionnels"""
    from models import Alert
    
    query = db.query(Alert)
    
    if processed is not None:
        query = query.filter(Alert.processed == processed)
    
    if zone_id:
        query = query.filter(Alert.zone_id == zone_id)
    
    alerts = query.order_by(Alert.created_at.desc()).all()
    return {"alerts": [a.to_dict() for a in alerts]}

@app.post("/alerts/{alert_id}/mark-processed")
def mark_alert_processed(alert_id: str, db: Session = Depends(get_db)):
    """Marquer une alerte comme traitée"""
    from models import Alert
    from datetime import datetime
    
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alerte non trouvée")
    
    alert.processed = True
    alert.processed_at = datetime.now()
    alert.broadcast_count += 1
    
    db.commit()
    db.refresh(alert)
    return alert.to_dict()

# ===========================
# MARKET ENDPOINTS
# ===========================

@app.get("/market")
def list_market_items(zone_id: str = None, product: str = None, db: Session = Depends(get_db)):
    """Liste prix marché avec filtres"""
    from models import MarketItem
    
    query = db.query(MarketItem)
    
    if zone_id:
        query = query.filter(MarketItem.zone_id == zone_id)
    
    if product:
        query = query.filter(MarketItem.product_name.ilike(f"%{product}%"))
    
    items = query.order_by(MarketItem.date.desc()).limit(50).all()
    return {"market_items": [i.to_dict() for i in items]}

# ===========================
# WEATHER ENDPOINTS
# ===========================

@app.post("/weather")
def create_weather_data(data: dict, db: Session = Depends(get_db)):
    """Enregistrer données météo"""
    from models import WeatherData
    import uuid
    from datetime import datetime
    
    weather = WeatherData(
        id=str(uuid.uuid4()),
        zone_id=data["zone_id"],
        temperature=data.get("temperature"),
        precipitation=data.get("precipitation"),
        humidity=data.get("humidity"),
        wind_speed=data.get("wind_speed"),
        forecast_date=data["forecast_date"],
        created_at=datetime.now()
    )
    
    db.add(weather)
    db.commit()
    db.refresh(weather)
    return weather.to_dict()

# ===========================
# STATS ENDPOINTS
# ===========================

@app.get("/stats")
def get_statistics(db: Session = Depends(get_db)):
    """Statistiques globales"""
    from models import User, Alert, Zone
    
    total_users = db.query(User).count()
    total_alerts = db.query(Alert).count()
    unprocessed_alerts = db.query(Alert).filter(Alert.processed == False).count()
    total_zones = db.query(Zone).count()
    
    return {
        "total_users": total_users,
        "total_alerts": total_alerts,
        "unprocessed_alerts": unprocessed_alerts,
        "total_zones": total_zones
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
