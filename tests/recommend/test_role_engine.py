from db.client import get_pg_connection
import recommend.engine as engine


class FakeCollection:
    def count(self): return 1
    def query(self, **kwargs): return {"ids": [["a1"]], "distances": [[0.2]]}


def test_role_call_adds_reason_without_breaking_legacy_shape(isolated_runtime, monkeypatch):
    conn = get_pg_connection()
    conn.execute("INSERT INTO users (id, name) VALUES ('u1', 'An')")
    conn.execute("INSERT INTO assets (id, type, title, source_tool, owner_id, usage_count) VALUES ('a1', 'prompt', 'Risk prompt', 'claude', 'u1', 0)")
    conn.execute("INSERT INTO asset_versions (id, asset_id, version_number, content) VALUES ('v1', 'a1', 1, 'risk checks')")
    conn.execute("UPDATE assets SET current_version_id='v1' WHERE id='a1'")
    conn.execute("INSERT INTO rationale (id, version_id, problem, failed_attempts, constraints, confidence) VALUES ('r1', 'v1', 'reduce risk', '[]', '[]', 'user_provided')")
    conn.commit(); conn.close()
    monkeypatch.setattr(engine, "get_vector_collection", lambda: FakeCollection())
    monkeypatch.setattr(engine, "resolve_role_lens", lambda role: {"role": role, "goals": ["risk"], "ranking_weights": {"role": 0.1}})

    legacy = engine.recommend("checks")
    aware = engine.recommend("checks", role="Manager")

    assert "role_reason" not in legacy[0]
    assert aware[0]["role_reason"] == "Matches role goal: risk"
