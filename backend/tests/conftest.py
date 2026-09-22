import os
from pathlib import Path


TEST_DATABASE = Path("/private/tmp/vocal-biomarkers-pytest.db")
TEST_DATABASE.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE}"
# Never load a real Whisper model in the offline suite -- no model weights on disk,
# no network guaranteed, and it would slow every WS test down regardless.
os.environ["MOCK_WHISPER"] = "1"
