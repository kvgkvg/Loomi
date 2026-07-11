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
    } <= names


def test_vector_collection_is_persistent(isolated_runtime):
    from db.client import get_vector_collection

    assert get_vector_collection().name == "organizational_memory"
