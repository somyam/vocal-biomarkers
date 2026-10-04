"""Small, idempotent additive migrations for existing prototype databases."""
from sqlalchemy import inspect, text


def migrate_recording_completion(engine):
    # Fresh databases already have this column through metadata.create_all().
    # Keep the ALTER and backfill transactional on Postgres; never recreate tables.
    with engine.begin() as connection:
        columns = {column['name'] for column in inspect(connection).get_columns('checkins')}
        if 'recording_completed_at' not in columns:
            connection.execute(text('ALTER TABLE checkins ADD COLUMN recording_completed_at TIMESTAMP NULL'))
        connection.execute(text('UPDATE checkins SET recording_completed_at = completed_at '
                                'WHERE recording_completed_at IS NULL AND completed_at IS NOT NULL'))
