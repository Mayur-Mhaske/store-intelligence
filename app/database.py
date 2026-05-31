from sqlalchemy import create_engine, Column, String, Float, Boolean, Integer, DateTime, JSON, text
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./store_intelligence.db")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class EventDB(Base):
    __tablename__ = "events"
    event_id      = Column(String, primary_key=True, index=True)
    store_id      = Column(String, index=True, nullable=False)
    camera_id     = Column(String, nullable=False)
    visitor_id    = Column(String, index=True, nullable=False)
    event_type    = Column(String, nullable=False)
    timestamp     = Column(DateTime, nullable=False, index=True)
    zone_id       = Column(String, nullable=True)
    dwell_ms      = Column(Integer, default=0)
    is_staff      = Column(Boolean, default=False)
    confidence    = Column(Float, nullable=False)
    metadata_json = Column(JSON, default={})
    ingested_at   = Column(DateTime, default=datetime.utcnow)


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_db_health() -> str:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return "healthy"
    except Exception as e:
        return f"unhealthy: {str(e)}"
