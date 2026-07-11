import importlib

from db import client_stub


def test_seed_populates_sql_and_vectors(tmp_path, monkeypatch):
    monkeypatch.setattr(client_stub, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(client_stub, "CHROMA_PATH", str(tmp_path / "chroma"))
    seed_mod = importlib.import_module("scripts.seed_recommend")

    n = seed_mod.seed()
    assert n >= 5

    conn = client_stub.get_pg_connection()
    rows = conn.execute("SELECT COUNT(*) AS c FROM assets").fetchone()["c"]
    assert rows == n

    col = client_stub.get_vector_collection()
    assert col.count() == n
