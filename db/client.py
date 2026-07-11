"""Shared DB client — everyone imports from here, nobody connects on their own.

Usage:
    from db.client import get_pg_connection, get_vector_collection

    conn = get_pg_connection()            # sqlite3.Connection (rows behave like dicts)
    collection = get_vector_collection()  # Chroma collection "assets"

Backend: DATABASE_URL selects PostgreSQL; SQLite remains the zero-setup fallback.
CHROMA_HOST selects remote Chroma; otherwise Chroma runs embedded/persistent.

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
COLLECTION_NAME = "assets"

_SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"
_POSTGRES_SCHEMA_FILE = Path(__file__).resolve().parent / "schema.postgres.sql"


def _placeholders(query: str) -> str:
    return query.replace("?", "%s")


class _PostgresRow:
    def __init__(self, columns, values):
        self._columns = columns
        self._values = tuple(values)

    def __getitem__(self, key):
        if isinstance(key, str):
            key = self._columns.index(key)
        return self._values[key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return self._columns


class _PostgresCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query, params=()):
        self._cursor.execute(_placeholders(query), params)
        return self

    def _row(self, row):
        if row is None or isinstance(row, _PostgresRow):
            return row
        columns = [getattr(column, "name", column[0]) for column in self._cursor.description]
        if isinstance(row, dict):
            return _PostgresRow(columns, [row[column] for column in columns])
        return _PostgresRow(columns, row)

    def fetchone(self):
        return self._row(self._cursor.fetchone())

    def fetchall(self):
        return [self._row(row) for row in self._cursor.fetchall()]

    def __iter__(self):
        return (self._row(row) for row in self._cursor)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _PostgresConnection:
    def __init__(self, connection):
        self._connection = connection

    def execute(self, query, params=()):
        return self.cursor().execute(query, params)

    def cursor(self):
        return _PostgresCursor(self._connection.cursor())

    def __getattr__(self, name):
        return getattr(self._connection, name)


def _connect_postgres(database_url: str):
    import psycopg

    return psycopg.connect(database_url)


def _db_path() -> str:
    # Read at call time so tests (LOOMI_DB_PATH set per-test) get isolated paths.
    return os.environ.get("LOOMI_DB_PATH", str(_REPO_ROOT / "db" / "loomi.db"))


def _chroma_path() -> str:
    return os.environ.get("LOOMI_CHROMA_PATH", str(_REPO_ROOT / "db" / "chroma"))


def get_pg_connection():
    """Return a ready-to-use DB connection. Schema is auto-applied (idempotent)."""
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        connection = _connect_postgres(database_url)
        connection.execute(_POSTGRES_SCHEMA_FILE.read_text())
        connection.commit()
        return _PostgresConnection(connection)

    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row  # rows accessible by column name
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA_FILE.read_text())
    return conn


def get_vector_collection():
    """Return the shared Chroma collection (persistent, local, no server needed).

    Embeddings are Chroma-managed: callers pass documents=/query_texts= and Chroma
    embeds with its default function (all-MiniLM-L6-v2 ONNX). Do NOT pass your own
    embeddings — one embedding backend for the whole team.
    """
    import chromadb

    host = os.environ.get("CHROMA_HOST")
    client = (
        chromadb.HttpClient(
            host=host,
            port=int(os.environ.get("CHROMA_PORT", "8000")),
        )
        if host
        else chromadb.PersistentClient(path=_chroma_path())
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
