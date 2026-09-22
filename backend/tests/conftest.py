import os
from pathlib import Path


TEST_DATABASE = Path("/private/tmp/vocal-biomarkers-pytest.db")
TEST_DATABASE.unlink(missing_ok=True)
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DATABASE}"
