import os

import pytest

from capture_pipeline.llm import extract_rationale


@pytest.mark.live
def test_featherless_returns_valid_rationale():
    if os.getenv("RUN_FEATHERLESS_LIVE") != "1":
        pytest.skip("set RUN_FEATHERLESS_LIVE=1 to spend API credits")
    if not os.getenv("FEATHERLESS_API_KEY"):
        pytest.skip("FEATHERLESS_API_KEY is not set")

    result = extract_rationale(
        "Classify support tickets into billing or technical queues.",
        "Changed output to strict JSON after free-form labels broke automation.",
    )

    assert result["problem"]
    assert result["confidence"] == "auto"
