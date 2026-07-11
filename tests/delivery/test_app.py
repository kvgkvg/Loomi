def test_delivery_app_exports_main_without_importing_streamlit():
    from delivery.app import main
    assert callable(main)
