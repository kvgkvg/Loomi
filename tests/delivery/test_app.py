import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


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


def test_delivery_script_bootstraps_project_import_path():
    script = PROJECT_ROOT / "delivery" / "app.py"
    code = (
        "import runpy,sys; "
        f"root={str(PROJECT_ROOT)!r}; delivery={str(script.parent)!r}; "
        "sys.path=[delivery]+[p for p in sys.path if p not in ('', root)]; "
        f"runpy.run_path({str(script)!r}, run_name='delivery_import_test'); "
        "print('import-ok')"
    )

    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
    assert "import-ok" in result.stdout
