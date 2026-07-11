def test_connection_initializes_required_tables(isolated_runtime):
    from db.client import get_pg_connection

    conn = get_pg_connection()
    names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert {
        "raw_events",
        "users",
        "assets",
        "asset_versions",
        "rationale",
        "asset_usage",
        "tags",
        "asset_tags",
        "conversations",
        "conversation_turns",
        "turn_feedback",
        "rationale_statements",
        "rationale_statement_turns",
        "rationale_statement_versions",
        "rationale_statement_commits",
    } <= names


def test_rationale_statement_review_status_is_constrained(isolated_runtime):
    from db.client import get_pg_connection

    conn = get_pg_connection()
    try:
        conn.execute(
            "INSERT INTO rationale_statements "
            "(id, statement_type, statement, original_statement, evidence_kind, confidence, review_status) "
            "VALUES ('s1', 'intent', 'x', 'x', 'inferred', 0.5, 'invalid')"
        )
    except Exception as exc:
        assert "CHECK constraint failed" in str(exc)
    else:
        raise AssertionError("invalid review status was accepted")


def test_connection_creates_configured_parent_directory(tmp_path, monkeypatch):
    from db.client import get_pg_connection

    db_path = tmp_path / "nested" / "runtime" / "loomi.sqlite3"
    monkeypatch.setenv("LOOMI_DB_PATH", str(db_path))

    connection = get_pg_connection()
    connection.close()

    assert db_path.exists()


def test_vector_collection_is_persistent(isolated_runtime):
    from db.client import get_vector_collection, COLLECTION_NAME

    assert COLLECTION_NAME == "assets"
    assert get_vector_collection().name == "assets"
