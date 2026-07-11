"""Recommend engine tests — run against Khang's canonical seed data.

Uses the isolated_runtime fixture (conftest) which points LOOMI_DB_PATH /
LOOMI_CHROMA_PATH at a tmp dir, so each test seeds a fresh DB + Chroma.
Embeddings are Chroma-managed (default model); first run downloads it.
"""
from db.seed import seed
from recommend.engine import recommend


def test_empty_query_returns_empty_list(isolated_runtime):
    seed()
    assert recommend("") == []
    assert recommend("   ") == []


def test_semantic_match_surfaces_an_asset(isolated_runtime):
    seed()
    # Phrased differently from any seeded title; An owns the closest assets
    # (support-ticket triage / lead-qualification). Proves meaning-based match.
    res = recommend("build a lead-classification agent for sales", top_k=5)
    assert res
    assert res[0]["owner_name"] == "An"


def test_output_shape_and_sorted(isolated_runtime):
    seed()
    res = recommend("categorize incoming support messages into buckets", top_k=5)
    assert res
    assert len(res) <= 5
    keys = {"asset_id", "title", "problem", "score", "usage_count", "owner_name"}
    for r in res:
        assert keys == set(r)
        assert isinstance(r["score"], float)
        assert 0.0 <= r["score"] <= 1.0
    scores = [r["score"] for r in res]
    assert scores == sorted(scores, reverse=True)
