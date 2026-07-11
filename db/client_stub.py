"""TEMP local stand-in for Khang's db/client.py.

Same public function names (get_pg_connection, get_vector_collection) so
engine.py only needs its import line swapped at integration. Uses SQLite +
a persistent local Chroma so the recommend engine is fully testable now.
"""
import os
import sqlite3

import chromadb

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".data")
DB_PATH = os.path.join(_DATA_DIR, "stub.db")
CHROMA_PATH = os.path.join(_DATA_DIR, "chroma")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  email TEXT UNIQUE,
  team TEXT
);
CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  title TEXT NOT NULL,
  source_tool TEXT NOT NULL,
  owner_id TEXT REFERENCES users(id),
  current_version_id TEXT,
  usage_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS asset_versions (
  id TEXT PRIMARY KEY,
  asset_id TEXT REFERENCES assets(id),
  version_number INTEGER NOT NULL,
  content TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rationale (
  id TEXT PRIMARY KEY,
  version_id TEXT UNIQUE REFERENCES asset_versions(id),
  problem TEXT,
  confidence TEXT
);
"""


def get_pg_connection() -> sqlite3.Connection:
    os.makedirs(_DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def get_vector_collection():
    os.makedirs(CHROMA_PATH, exist_ok=True)
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(
        name="assets", metadata={"hnsw:space": "cosine"}
    )
