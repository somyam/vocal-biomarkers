"""Small authenticated API for the vocal-biomarkers prototype."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .api import checkins, interventions, signals, stream, webhooks
from .core.config import settings
from .core.database import Base, SessionLocal, engine
from .models import Intervention, User, UserIntervention
from .services.transcribe import transcriber

DEFAULT_INTERVENTIONS = {
    "hydrate": "Drink a glass of water before coffee.",
    "liposomal-glutathione": "Complete your morning glutathione protocol.",
    "morning-light": "Spend time in natural morning light.",
    "morning-checkin": "Find a quiet space and record a one-minute Morning Check-in.",
    "meditation": "Take ten quiet minutes to meditate.",
    "cold-plunge": "Complete your planned cold-plunge clinic visit.",
    "workout": "Complete your planned workout.",
}


def seed_prototype_data() -> None:
    with SessionLocal() as db:
        if not db.get(User, "mvp-user"):
            db.add(User(user_id="mvp-user", member=True))
        for intervention_id, guide_text in DEFAULT_INTERVENTIONS.items():
            if not db.get(Intervention, intervention_id):
                db.add(Intervention(intervention_id=intervention_id, guide_text=guide_text))
            active_link = db.scalar(select(UserIntervention).where(
                UserIntervention.user_id == "mvp-user",
                UserIntervention.intervention_id == intervention_id,
                UserIntervention.active.is_(True),
            ))
            if active_link is None:
                db.add(UserIntervention(user_id="mvp-user", intervention_id=intervention_id, active=True))
        db.commit()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_prototype_data()
    # Fire-and-forget: pays Whisper's one-time first-inference cost now, off the
    # request path, so it's not the first live check-in stream that eats it.
    asyncio.create_task(asyncio.to_thread(transcriber().warm_up))
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Vocal Biomarkers API", version="0.2.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware,
        allow_origins=[item.strip() for item in settings().cors_origin.split(",") if item.strip()],
        allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(checkins.router)
    app.include_router(stream.router)
    app.include_router(interventions.router)
    app.include_router(signals.router)
    app.include_router(webhooks.router)
    return app


app = create_app()
