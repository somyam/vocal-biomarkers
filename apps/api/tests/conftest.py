import os
import tempfile
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url


# Use a fresh schema in an explicitly supplied Postgres database, never its public
# tables. The default offline suite uses its own temporary SQLite database.
_test_directory = tempfile.TemporaryDirectory(prefix="vocal-biomarkers-tests-")
_postgres_url = os.environ.get("TEST_POSTGRES_URL")
_schema = f"test_vocal_{uuid.uuid4().hex}"
_admin_engine = None
if _postgres_url:
    _admin_engine = create_engine(_postgres_url)
    with _admin_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{_schema}"'))
    os.environ["DATABASE_URL"] = make_url(_postgres_url).update_query_dict(
        {"options": f"-csearch_path={_schema}"}
    ).render_as_string(hide_password=False)
else:
    os.environ["DATABASE_URL"] = f"sqlite:///{Path(_test_directory.name) / 'test.db'}"

# Tests must never submit audio using credentials from the developer's .env.
os.environ["AMPLIFIER_ACCOUNT_ID"] = ""
os.environ["AMPLIFIER_API_KEY"] = ""
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["ANTHROPIC_API"] = ""
os.environ["APP_API_TOKEN"] = "development-token"
os.environ["MOCK_WHISPER"] = "1"


@pytest.fixture(scope="session", autouse=True)
def isolated_database():
    from app.core.database import Base, engine
    from app import models  # noqa: F401 -- register all tables

    Base.metadata.create_all(engine)
    yield
    engine.dispose()
    if _admin_engine is not None:
        with _admin_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{_schema}" CASCADE'))
        _admin_engine.dispose()
    _test_directory.cleanup()
