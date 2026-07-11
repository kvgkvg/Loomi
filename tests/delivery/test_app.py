def test_delivery_app_exports_main_without_importing_streamlit():
    from delivery.app import main
    assert callable(main)


def test_delivery_app_loads_project_env(tmp_path, monkeypatch):
    from delivery.app import _load_runtime_env

    env_file = tmp_path / ".env"
    env_file.write_text("LOOMI_UI_TEST_VALUE=loaded\n", encoding="utf-8")
    monkeypatch.delenv("LOOMI_UI_TEST_VALUE", raising=False)

    _load_runtime_env(env_file)

    assert __import__("os").environ["LOOMI_UI_TEST_VALUE"] == "loaded"
