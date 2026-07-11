"""Project-wide SQLite and Chroma connection factories."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path


DEFAULT_DB_PATH = ".loomi/loomi.sqlite3"
DEFAULT_CHROMA_PATH = ".loomi/chroma"
VECTOR_COLLECTION_NAME = "organizational_memory"

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_events (
    id TEXT PRIMARY KEY,
    source_tool TEXT NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    raw_signal TEXT,
    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed INTEGER NOT NULL DEFAULT 0,
    processed_asset_version_id TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE,
    team TEXT
);

CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    asset_key TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('prompt', 'workflow', 'agent_config')),
    title TEXT NOT NULL,
    source_tool TEXT NOT NULL,
    owner_id TEXT REFERENCES users(id),
    previous_asset_id TEXT REFERENCES assets(id),
    current_version_id TEXT,
    usage_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS asset_versions (
    id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    raw_event_id TEXT REFERENCES raw_events(id),
    version_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    diff_summary TEXT,
    editor_id TEXT REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset_id, version_number)
);

CREATE TABLE IF NOT EXISTS rationale (
    id TEXT PRIMARY KEY,
    version_id TEXT UNIQUE NOT NULL REFERENCES asset_versions(id) ON DELETE CASCADE,
    problem TEXT,
    failed_attempts TEXT NOT NULL DEFAULT '[]',
    constraints TEXT NOT NULL DEFAULT '[]',
    confidence TEXT CHECK (confidence IN ('auto', 'user_provided'))
);

CREATE TABLE IF NOT EXISTS tags (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS asset_tags (
    asset_id TEXT REFERENCES assets(id) ON DELETE CASCADE,
    tag_id TEXT REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (asset_id, tag_id)
);

CREATE TABLE IF NOT EXISTS asset_usage (
    id TEXT PRIMARY KEY,
    asset_id TEXT REFERENCES assets(id) ON DELETE CASCADE,
    user_id TEXT REFERENCES users(id),
    task_description TEXT,
    used_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def _runtime_path(variable: str, default: str) -> Path:
    path = Path(os.getenv(variable, default)).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_pg_connection() -> sqlite3.Connection:
    """Return initialized SQLite connection using shared team contract name."""
    path = _runtime_path("LOOMI_DB_PATH", DEFAULT_DB_PATH)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    return connection


def get_vector_collection():
    """Return persistent Chroma collection shared by capture and recommend code."""
    import chromadb

    path = _runtime_path("LOOMI_CHROMA_PATH", DEFAULT_CHROMA_PATH)
    client = chromadb.PersistentClient(path=str(path))
    return client.get_or_create_collection(VECTOR_COLLECTION_NAME)
