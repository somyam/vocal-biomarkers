import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .database import Base


def uid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    member: Mapped[bool] = mapped_column(Boolean, default=True)


class CheckIn(Base):
    __tablename__ = "checkins"
    checkin_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[float] = mapped_column(default=0.0)
    pulse_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Recording(Base):
    __tablename__ = "recordings"
    recording_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    checkin_id: Mapped[str] = mapped_column(ForeignKey("checkins.checkin_id"), unique=True, index=True)
    audio_wav: Mapped[bytes] = mapped_column(LargeBinary)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AmplifierJob(Base):
    __tablename__ = "amplifier_jobs"
    job_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    checkin_id: Mapped[str] = mapped_column(ForeignKey("checkins.checkin_id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    errors: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Intervention(Base):
    __tablename__ = "interventions"
    intervention_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    guide_text: Mapped[str] = mapped_column(Text)


class UserIntervention(Base):
    __tablename__ = "user_interventions"
    user_intervention_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    intervention_id: Mapped[str] = mapped_column(ForeignKey("interventions.intervention_id"), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
