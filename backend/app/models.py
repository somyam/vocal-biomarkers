import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from .database import Base


def uid() -> str:
    return str(uuid.uuid4())


class CheckIn(Base):
    __tablename__ = "checkins"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String(64), default="mvp-user", index=True)
    status: Mapped[str] = mapped_column(String(24), default="created", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[float] = mapped_column(default=0.0)
    pulse_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    quality_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    trend_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Recording(Base):
    __tablename__ = "recordings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    checkin_id: Mapped[str] = mapped_column(ForeignKey("checkins.id"), unique=True, index=True)
    wav_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    sample_rate: Mapped[int] = mapped_column(default=16000)
    duration_seconds: Mapped[float] = mapped_column(default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CheckInSegment(Base):
    __tablename__ = "checkin_segments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    checkin_id: Mapped[str] = mapped_column(ForeignKey("checkins.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    start_seconds: Mapped[float] = mapped_column()
    end_seconds: Mapped[float] = mapped_column()
    wav_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(24), default="queued")


class AmplifierJob(Base):
    __tablename__ = "amplifier_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    checkin_id: Mapped[str] = mapped_column(ForeignKey("checkins.id"), index=True)
    segment_id: Mapped[str] = mapped_column(ForeignKey("checkin_segments.id"), index=True)
    provider_job_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued")
    raw_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Habit(Base):
    __tablename__ = "habits"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(String(64), default="mvp-user", index=True)
    name: Mapped[str] = mapped_column(String(120))
    frequency: Mapped[str] = mapped_column(String(16), default="daily")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class HabitCompletion(Base):
    __tablename__ = "habit_completions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    habit_id: Mapped[str | None] = mapped_column(ForeignKey("habits.id"), nullable=True, index=True)
    habit_name: Mapped[str] = mapped_column(String(120))
    checkin_id: Mapped[str | None] = mapped_column(ForeignKey("checkins.id"), nullable=True, unique=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    source: Mapped[str] = mapped_column(String(32), default="manual")


class ReminderSetting(Base):
    __tablename__ = "reminder_settings"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True, default="mvp-user")
    time_local: Mapped[str] = mapped_column(String(8), default="08:00")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
