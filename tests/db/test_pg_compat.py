import os
import uuid
import pytest
from db.client import get_pg_connection

@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
def test_database_contract(backend, monkeypatch, tmp_path):
    if backend == "sqlite":
        # SQLite mode
        monkeypatch.setenv("LOOMI_DB_PATH", str(tmp_path / "test_loomi.sqlite"))
        monkeypatch.delenv("DATABASE_URL", raising=False)
    else:
        # Postgres mode
        pg_url = os.environ.get("DATABASE_URL")
        if not pg_url:
            # Fallback to local default database created earlier
            pg_url = "postgresql://postgres@localhost:5432/loomi_test"
        
        # Test connection first to verify availability
        try:
            import psycopg
            conn = psycopg.connect(pg_url)
            conn.close()
        except Exception as e:
            pytest.skip(f"PostgreSQL database not available: {e}")
            
        monkeypatch.setenv("DATABASE_URL", pg_url)

    # 1. Connect and verify auto-migration
    conn = get_pg_connection()
    assert conn is not None

    # Verify tables exist
    cursor = conn.cursor()
    if backend == "sqlite":
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
    else:
        cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
        tables = {row[0] for row in cursor.fetchall()}

    required_tables = {
        "raw_events",
        "users",
        "assets",
        "asset_versions",
        "rationale",
        "git_poll_state"
    }
    assert required_tables <= tables

    # WIPE tables for isolated test run
    for table in ["git_poll_state", "rationale", "asset_versions", "assets", "raw_events", "users"]:
        cursor.execute(f"DELETE FROM {table}")
    conn.commit()

    # 2. Insert test user and test compatibility of primary keys
    user_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO users (id, name, email, team) VALUES (?, ?, ?, ?)",
        (user_id, "Test User", "test@loomi.ai", "Engineering")
    )
    conn.commit()

    # Query and test row access by index and key
    cursor.execute("SELECT id, name, email, team FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == user_id
    assert row[1] == "Test User"
    assert row["name"] == "Test User"
    assert row["email"] == "test@loomi.ai"
    assert row["team"] == "Engineering"

    # 3. Test boolean type inserting and query casting compatibility (0/1 vs TRUE/FALSE)
    event_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO raw_events (id, source_tool, title, content, processed) VALUES (?, ?, ?, ?, 0)",
        (event_id, "git", "Test Commit", "test content")
    )
    conn.commit()

    cursor.execute("SELECT processed FROM raw_events WHERE id = ?", (event_id,))
    row = cursor.fetchone()
    # Python treats True == 1 and False == 0 as equal
    assert row[0] == 0
    assert row["processed"] == 0

    # Test update to 1 (True)
    cursor.execute(
        "UPDATE raw_events SET processed = 1 WHERE id = ?",
        (event_id,)
    )
    conn.commit()

    cursor.execute("SELECT processed FROM raw_events WHERE id = ?", (event_id,))
    row = cursor.fetchone()
    assert row[0] == 1
    assert row["processed"] == 1

    # 4. Test JSONB / text serialization compatibility
    asset_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO assets (id, type, title, source_tool, owner_id) VALUES (?, 'prompt', ?, 'git', ?)",
        (asset_id, "Test Asset", user_id)
    )
    version_id = str(uuid.uuid4())
    cursor.execute(
        "INSERT INTO asset_versions (id, asset_id, version_number, content) VALUES (?, ?, 1, ?)",
        (version_id, asset_id, "some version content")
    )
    
    rat_id = str(uuid.uuid4())
    import json
    constraints_json = json.dumps(["constraint1", "constraint2"])
    cursor.execute(
        "INSERT INTO rationale (id, version_id, problem, constraints, confidence) VALUES (?, ?, ?, ?, 'auto')",
        (rat_id, version_id, "some problem", constraints_json)
    )
    conn.commit()

    cursor.execute("SELECT constraints FROM rationale WHERE id = ?", (rat_id,))
    row = cursor.fetchone()
    val = row["constraints"]
    
    # Check that we can extract constraints cleanly
    from onboarding.assistant import _as_constraints
    parsed_constraints = _as_constraints(val)
    assert parsed_constraints == ["constraint1", "constraint2"]

    # 5. Test the new git_poll_state table
    repo_path = "/home/user/repo"
    sha = "abc123xyz"
    cursor.execute(
        "INSERT INTO git_poll_state (repo_path, last_polled_sha) VALUES (?, ?)",
        (repo_path, sha)
    )
    conn.commit()

    cursor.execute("SELECT repo_path, last_polled_sha FROM git_poll_state WHERE repo_path = ?", (repo_path,))
    row = cursor.fetchone()
    assert row is not None
    assert row["last_polled_sha"] == sha
    assert row[0] == repo_path

    cursor.close()
    conn.close()
