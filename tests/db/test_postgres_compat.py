from db import client


class FakeCursor:
    description = [("id",), ("title",)]

    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, params=()):
        self.connection.last_query = query
        self.connection.last_params = params
        return self

    def fetchone(self):
        return ("a-1", "Prompt")

    def fetchall(self):
        return [("a-1", "Prompt")]

    def close(self):
        pass


class FakePostgresConnection:
    def __init__(self):
        self.last_query = None
        self.last_params = None
        self.commits = 0

    def cursor(self):
        return FakeCursor(self)

    def execute(self, query, params=()):
        return self.cursor().execute(query, params)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


def postgres_connection(monkeypatch):
    connection = FakePostgresConnection()
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    monkeypatch.setattr(client, "_connect_postgres", lambda _: connection)
    return connection, client.get_pg_connection()


def test_postgres_adapter_accepts_sqlite_style_placeholders(monkeypatch):
    connection, adapted = postgres_connection(monkeypatch)

    adapted.execute("SELECT * FROM assets WHERE id = ?", ("a-1",))

    assert connection.last_query == "SELECT * FROM assets WHERE id = %s"
    assert connection.last_params == ("a-1",)


def test_postgres_adapter_rows_support_names_and_indexes(monkeypatch):
    _, adapted = postgres_connection(monkeypatch)

    row = adapted.cursor().execute("SELECT id, title FROM assets").fetchone()

    assert row["id"] == row[0] == "a-1"
    assert row["title"] == row[1] == "Prompt"


def test_remote_chroma_selected_from_environment(monkeypatch):
    calls = []

    class FakeClient:
        def get_or_create_collection(self, **kwargs):
            calls.append(kwargs)
            return "collection"

    class FakeChroma:
        def HttpClient(self, **kwargs):
            calls.append(kwargs)
            return FakeClient()

    monkeypatch.setenv("CHROMA_HOST", "chroma")
    monkeypatch.setenv("CHROMA_PORT", "9000")
    monkeypatch.setitem(__import__("sys").modules, "chromadb", FakeChroma())

    assert client.get_vector_collection() == "collection"
    assert calls == [
        {"host": "chroma", "port": 9000},
        {"name": "assets", "metadata": {"hnsw:space": "cosine"}},
    ]
