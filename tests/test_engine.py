import importlib

from db import client_stub


def _seed(tmp_path, monkeypatch):
    monkeypatch.setattr(client_stub, "DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr(client_stub, "CHROMA_PATH", str(tmp_path / "chroma"))
    importlib.import_module("scripts.seed_recommend").seed()


def test_empty_query_returns_empty_list(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from recommend.engine import recommend
    assert recommend("") == []
    assert recommend("   ") == []


def test_semantic_match_ranks_support_bot_top(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from recommend.engine import recommend
    res = recommend("build a lead-classification agent for sales", top_k=3)
    assert res  # non-empty
    assert res[0]["asset_id"] == "a-support-bot"


def test_output_shape_and_sorted(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from recommend.engine import recommend
    res = recommend("categorize incoming messages", top_k=5)
    assert len(res) <= 5
    keys = {"asset_id", "title", "problem", "score", "usage_count", "owner_name"}
    for r in res:
        assert keys == set(r)
        assert isinstance(r["score"], float)
    scores = [r["score"] for r in res]
    assert scores == sorted(scores, reverse=True)


def test_owner_name_resolved(tmp_path, monkeypatch):
    _seed(tmp_path, monkeypatch)
    from recommend.engine import recommend
    res = recommend("triage support tickets", top_k=1)
    assert res[0]["owner_name"] == "An"
