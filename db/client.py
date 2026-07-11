"""Shared DB client — everyone imports from here, nobody connects on their own.

Usage:
    from db.client import get_pg_connection, get_vector_collection

    conn = get_pg_connection()            # sqlite3.Connection (rows behave like dicts)
    collection = get_vector_collection()  # Chroma collection "assets"

Backend: SQLite (chosen over Postgres for hackathon speed — same schema,
task.md explicitly allows it). Chroma runs embedded/persistent, no server.

Embedding model: Chroma's default embedding function is
sentence-transformers/all-MiniLM-L6-v2 (ONNX build) — exactly the model the
team agreed on. Just call collection.add(documents=...) / .query(query_texts=...)
and Chroma embeds with that model. DO NOT pass your own embeddings from a
different model.

Config via .env (optional): LOOMI_DB_PATH, LOOMI_CHROMA_PATH.
Defaults live inside the repo, so it works with zero setup.
"""

import os
import sqlite3
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

DB_PATH = os.environ.get("LOOMI_DB_PATH", str(_REPO_ROOT / "db" / "loomi.db"))
CHROMA_PATH = os.environ.get("LOOMI_CHROMA_PATH", str(_REPO_ROOT / "db" / "chroma"))
COLLECTION_NAME = "assets"

_SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"


def get_pg_connection() -> sqlite3.Connection:
    """Return a ready-to-use DB connection. Schema is auto-applied (idempotent)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # rows accessible by column name
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA_FILE.read_text())
    return conn


def get_vector_collection():
    """Return the shared Chroma collection (persistent, local, no server needed)."""
    import chromadb

    client = chromadb.PersistentClient(path=CHROMA_PATH)
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
