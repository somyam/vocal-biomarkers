from sqlalchemy import create_engine, inspect, text
from app.core.migrations import migrate_recording_completion
from app.core.database import engine


def test_additive_migration_preserves_and_backfills_old_rows(tmp_path):
    old = create_engine(f'sqlite:///{tmp_path}/old.db')
    with old.begin() as connection:
        connection.execute(text('CREATE TABLE checkins (checkin_id TEXT PRIMARY KEY, completed_at TIMESTAMP, transcript TEXT)'))
        connection.execute(text("INSERT INTO checkins VALUES ('done', '2026-10-04 00:00:00', 'keep me'), ('pending', NULL, 'keep too')"))
    migrate_recording_completion(old)
    migrate_recording_completion(old)
    with old.connect() as connection:
        rows = connection.execute(text('SELECT * FROM checkins ORDER BY checkin_id')).mappings().all()
        assert rows[0]['recording_completed_at'] == rows[0]['completed_at']
        assert rows[0]['transcript'] == 'keep me'
        assert rows[1]['recording_completed_at'] is None
    old.dispose()


def test_migration_backfill_on_configured_isolated_database():
    from app.models import CheckIn, User
    from app.core.database import SessionLocal
    import uuid
    from datetime import datetime
    with SessionLocal() as db:
        user = User(user_id=str(uuid.uuid4()))
        db.add(user)
        db.flush()
        row = CheckIn(user_id=user.user_id, completed_at=datetime.now(), transcript='preserved')
        db.add(row)
        db.commit()
        checkin_id = row.checkin_id
    migrate_recording_completion(engine)
    with SessionLocal() as db:
        row = db.get(CheckIn, checkin_id)
        assert row.recording_completed_at == row.completed_at and row.transcript == 'preserved'
