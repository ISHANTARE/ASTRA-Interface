"""
ASTRA-Interface Platform — database.py
SQLAlchemy schema + CRUD helpers matching AWS RDS configurations.

Credential storage security model:
  - Platform passwords  → bcrypt hash via werkzeug  (one-way, in users table)
  - Space-Track password → Fernet AES-128 ciphertext  (reversible, in spacetrack_credentials)
"""
from __future__ import annotations

import os
import logging
import datetime
from pathlib import Path

from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base

import crypto as _crypto

logger = logging.getLogger(__name__)

# Fallback to local SQLite if DATABASE_URL is not set
DB_PATH = Path(__file__).parent / "astra_platform.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DB_PATH}"

DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)

# Configure Engine
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ── Models ───────────────────────────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, 
            "username": self.username, 
            "email": self.email, 
            "password": self.password, 
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None
        }

class SpaceTrackCredential(Base):
    __tablename__ = "spacetrack_credentials"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    st_username = Column(String(100), nullable=False)
    st_password = Column(String(200), nullable=False)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

class ActivityLog(Base):
    __tablename__ = "activity_log"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50), nullable=False)
    detail = Column(String(255))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)

# ── Users ────────────────────────────────────────────────────────────────────

def create_user(username: str, email: str, password_hash: str) -> int:
    with SessionLocal() as db:
        user = User(username=username, email=email, password=password_hash)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id

def get_user_by_username(username: str) -> dict | None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username).first()
        return user.to_dict() if user else None

def get_user_by_id(user_id: int) -> dict | None:
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        return user.to_dict() if user else None

# ── Space-Track Credentials ───────────────────────────────────────────────────

def save_spacetrack_creds(user_id: int, st_user: str, st_pass: str) -> None:
    encrypted_pass = _crypto.encrypt(st_pass)
    with SessionLocal() as db:
        cred = db.query(SpaceTrackCredential).filter(SpaceTrackCredential.user_id == user_id).first()
        if cred:
            cred.st_username = st_user
            cred.st_password = encrypted_pass
            cred.updated_at = datetime.datetime.utcnow()
        else:
            cred = SpaceTrackCredential(user_id=user_id, st_username=st_user, st_password=encrypted_pass)
            db.add(cred)
        db.commit()

def get_spacetrack_creds(user_id: int) -> dict | None:
    with SessionLocal() as db:
        cred = db.query(SpaceTrackCredential).filter(SpaceTrackCredential.user_id == user_id).first()
        if not cred:
            return None

        st_pass_stored = cred.st_password
        if _crypto.is_encrypted(st_pass_stored):
            try:
                st_pass_plain = _crypto.decrypt(st_pass_stored)
            except ValueError:
                logger.warning("ST credential decryption failed for user %s", user_id)
                return None
        else:
            logger.info("Legacy plaintext ST credential detected for user %s", user_id)
            st_pass_plain = st_pass_stored

        return {
            "st_username": cred.st_username,
            "st_password": st_pass_plain,
            "updated_at":  cred.updated_at.isoformat() if cred.updated_at else None,
        }

def _get_raw_st_password(user_id: int) -> str | None:
    with SessionLocal() as db:
        cred = db.query(SpaceTrackCredential).filter(SpaceTrackCredential.user_id == user_id).first()
        return cred.st_password if cred else None

# ── Activity Log ─────────────────────────────────────────────────────────────

def log_activity(user_id: int, action: str, detail: str = "") -> None:
    with SessionLocal() as db:
        log = ActivityLog(user_id=user_id, action=action, detail=detail)
        db.add(log)
        db.commit()

def get_recent_activity(user_id: int, limit: int = 10) -> list[dict]:
    with SessionLocal() as db:
        logs = db.query(ActivityLog).filter(ActivityLog.user_id == user_id).order_by(ActivityLog.id.desc()).limit(limit).all()
        return [
            {
                "id": log.id,
                "action": log.action,
                "detail": log.detail,
                "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S") if log.created_at else None
            } 
            for log in logs
        ]
