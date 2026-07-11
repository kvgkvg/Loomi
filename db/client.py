"""Shared DB client — everyone imports from here, nobody connects on their own.

Usage:
    from db.client import get_pg_connection, get_vector_collection

    conn = get_pg_connection()            # sqlite3.Connection or PostgresConnectionWrapper (rows behave like dicts)
    collection = get_vector_collection()  # Chroma collection "assets"

Backend: SQLite (default) / PostgreSQL (via DATABASE_URL).
Chroma runs embedded/persistent by default, or HTTP client via CHROMA_HOST.
"""

import os
import sqlite3
import sys
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
COLLECTION_NAME = "assets"

_SCHEMA_FILE = Path(__file__).resolve().parent / "schema.sql"
_SCHEMA_PG_FILE = Path(__file__).resolve().parent / "schema_pg.sql"


def _db_path() -> str:
    # Read at call time so tests (LOOMI_DB_PATH set per-test) get isolated paths.
    return os.environ.get("LOOMI_DB_PATH", str(_REPO_ROOT / "db" / "loomi.db"))


def _chroma_path() -> str:
    return os.environ.get("LOOMI_CHROMA_PATH", str(_REPO_ROOT / "db" / "chroma"))


def _clean_value(val):
    import uuid
    import json
    import decimal
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    if isinstance(val, decimal.Decimal):
        return float(val)
    return val


class CompatibleRow:
    def __init__(self, description, values):
        self._description = description
        self._values = values
        self._index_map = {desc.name: i for i, desc in enumerate(description)} if description else {}

    def __getitem__(self, key):
        if isinstance(key, int):
            return _clean_value(self._values[key])
        elif isinstance(key, str):
            if key in self._index_map:
                return _clean_value(self._values[self._index_map[key]])
            raise KeyError(key)
        else:
            raise TypeError(f"Row indices must be integers or strings, not {type(key).__name__}")

    def __len__(self):
        return len(self._values)

    def __iter__(self):
        return (_clean_value(v) for v in self._values)

    def keys(self):
        return list(self._index_map.keys())

    def values(self):
        return [_clean_value(v) for v in self._values]

    def items(self):
        return [(k, _clean_value(self._values[v])) for k, v in self._index_map.items()]

    def __repr__(self):
        return f"CompatibleRow({dict(self.items())})"


def compatible_row_factory(cursor):
    description = cursor.description
    def make_row(values):
        return CompatibleRow(description, values)
    return make_row


class PostgresCursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query, params=None):
        # 1. Translate '?' to '%s'
        translated_query = query.replace('?', '%s')
        
        # 2. Translate processed = 0 / 1 to processed = FALSE / TRUE
        translated_query = re.sub(r'\bprocessed\s*=\s*0\b', 'processed = FALSE', translated_query)
        translated_query = re.sub(r'\bprocessed\s*=\s*1\b', 'processed = TRUE', translated_query)
        
        # 3. Translate INSERT/UPDATE literal 0 or 1 in values
        if 'raw_events' in translated_query.lower():
            if 'insert' in translated_query.lower():
                translated_query = re.sub(r',\s*0\s*\)', ', FALSE)', translated_query)

        self._cursor.execute(translated_query, params)
        return self

    def executemany(self, query, params_seq):
        translated_query = query.replace('?', '%s')
        translated_query = re.sub(r'\bprocessed\s*=\s*0\b', 'processed = FALSE', translated_query)
        translated_query = re.sub(r'\bprocessed\s*=\s*1\b', 'processed = TRUE', translated_query)
        if 'raw_events' in translated_query.lower() and 'insert' in translated_query.lower():
            translated_query = re.sub(r',\s*0\s*\)', ', FALSE)', translated_query)
        self._cursor.executemany(translated_query, params_seq)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self):
        self._cursor.close()

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def __iter__(self):
        return iter(self._cursor)


class PostgresConnectionWrapper:
    def __init__(self, conn):
        self._conn = conn

    def cursor(self, *args, **kwargs):
        cur = self._conn.cursor(*args, **kwargs)
        return PostgresCursorWrapper(cur)

    def execute(self, query, params=None):
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def executescript(self, sql_script):
        cur = self._conn.cursor()
        try:
            cur.execute(sql_script)
        finally:
            cur.close()

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()

    def __getattr__(self, name):
        return getattr(self._conn, name)


def get_pg_connection():
    """Return a ready-to-use DB connection. Schema is auto-applied (idempotent)."""
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        try:
            import psycopg
            raw_conn = psycopg.connect(database_url, row_factory=compatible_row_factory)
            conn = PostgresConnectionWrapper(raw_conn)
            conn.executescript(_SCHEMA_PG_FILE.read_text())
            conn.commit()
            return conn
        except Exception as e:
            print(f"PostgreSQL connection/migration failed: {e}. Falling back to SQLite.", file=sys.stderr)

    # Fallback to SQLite
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row  # rows accessible by column name
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA_FILE.read_text())
    return conn


def get_vector_collection():
    """Return the shared Chroma collection (persistent local OR remote server).

    Embeddings are Chroma-managed: callers pass documents=/query_texts= and Chroma
    embeds with its default function (all-MiniLM-L6-v2 ONNX). Do NOT pass your own
    embeddings — one embedding backend for the whole team.
    """
    import chromadb

    chroma_host = os.environ.get("CHROMA_HOST")
    if chroma_host:
        chroma_port = int(os.environ.get("CHROMA_PORT") or 8000)
        client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
    else:
        client = chromadb.PersistentClient(path=_chroma_path())

    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )
