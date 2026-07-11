import sqlite3
from db import client_stub


def test_pg_connection_has_expected_tables(tmp_path, monkeypatch):
    monkeypatch.setattr(client_stub, "DB_PATH", str(tmp_path / "t.db"))
    conn = client_stub.get_pg_connection()
    names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert {"users", "assets", "asset_versions", "rationale"} <= names


def test_pg_connection_row_factory_is_row(tmp_path, monkeypatch):
    monkeypatch.setattr(client_stub, "DB_PATH", str(tmp_path / "t.db"))
    conn = client_stub.get_pg_connection()
    assert conn.row_factory is sqlite3.Row


def test_vector_collection_named_assets(tmp_path, monkeypatch):
    monkeypatch.setattr(client_stub, "CHROMA_PATH", str(tmp_path / "chroma"))
    col = client_stub.get_vector_collection()
    assert col.name == "assets"
