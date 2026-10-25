from datetime import datetime, date
from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy import JSON
from sqlalchemy.orm import relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(80), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    symptoms = relationship("SymptomEntry", back_populates="owner", cascade="all, delete-orphan")
    cycle_days = relationship("CycleDay", back_populates="owner", cascade="all, delete-orphan")
    cycle_profile = relationship("CycleProfile", back_populates="owner", cascade="all, delete-orphan", uselist=False)

class SymptomEntry(Base):
    __tablename__ = "symptom_entries"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    symptom = Column(String(100), nullable=False)
    recorded_on = Column(Date, nullable=False, default=date.today)
    severity = Column(Integer, nullable=False)
    duration_hours = Column(Float, nullable=True)
    description = Column(Text, nullable=True)
    sleep_quality = Column(Integer, nullable=True)  # legacy field retained for existing records
    sleep_hours = Column(Float, nullable=True)
    mood = Column(String(40), nullable=True)
    tags = Column(String(300), nullable=True)
    cycle_day = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    owner = relationship("User", back_populates="symptoms")

class CycleDay(Base):
    __tablename__ = "cycle_days"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    recorded_on = Column(Date, nullable=False, index=True)
    flow = Column(Integer, nullable=False, default=0)
    pain = Column(Integer, nullable=True)
    mood = Column(Integer, nullable=True)
    energy = Column(Integer, nullable=True)
    tags = Column(JSON, nullable=False, default=list)
    notes = Column(Text, nullable=True)
    owner = relationship("User", back_populates="cycle_days")

class CycleProfile(Base):
    __tablename__ = "cycle_profiles"
    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    data = Column(JSON, nullable=False, default=dict)
    owner = relationship("User", back_populates="cycle_profile")
