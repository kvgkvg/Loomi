import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def isolated_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOMI_DB_PATH", str(tmp_path / "loomi.sqlite3"))
    monkeypatch.setenv("LOOMI_CHROMA_PATH", str(tmp_path / "chroma"))
    return tmp_path
