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
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[float] = mapped_column(default=0.0)
    pulse_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set once transcription has been attempted, success or failure -- distinct from
    # `transcript` being null, which alone can't tell "not attempted yet" from "attempted,
    # got nothing." refresh_checkin gates completion on this being set, same as it gates
    # on every AmplifierJob being terminal, so the check-in doesn't complete missing either.
    transcribed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


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
    group_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    errors: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CheckInSignal(Base):
    """One row per Amplifier signal per check-in, keyed to the longitudinal group the
    check-in was scored against. `baseline_score`, `deviation_from_baseline`, `anomaly`,
    `z_score`, and `population_z` are `null` until that subject's group has an established
    baseline (Amplifier's own minimum: three spaced readings) — gate any display or
    analysis on `baseline_score is not None`, not on a locally tracked count."""
    __tablename__ = "checkin_signals"
    signal_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    checkin_id: Mapped[str] = mapped_column(ForeignKey("checkins.checkin_id"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), index=True)
    signal_name: Mapped[str] = mapped_column(String(64), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    score: Mapped[float]
    level: Mapped[str] = mapped_column(String(24))
    flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    latest_score: Mapped[float | None] = mapped_column(nullable=True)
    baseline_score: Mapped[float | None] = mapped_column(nullable=True)
    deviation_from_baseline: Mapped[float | None] = mapped_column(nullable=True)
    anomaly: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    z_score: Mapped[float | None] = mapped_column(nullable=True)
    population_z: Mapped[float | None] = mapped_column(nullable=True)


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
