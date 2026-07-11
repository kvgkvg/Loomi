import math
import pytest
from recommend.scoring import compute, role_adjusted, W_COS, W_CONF, W_USE


def test_weights_sum_to_one():
    assert math.isclose(W_COS + W_CONF + W_USE, 1.0)


def test_perfect_match_user_provided_high_usage_near_one():
    # cosine=1, user_provided conf=1.0, usage saturated -> 0.7+0.2+0.1
    assert compute(1.0, "user_provided", 20) == pytest.approx(1.0)


def test_user_provided_beats_auto_all_else_equal():
    assert compute(0.5, "user_provided", 0) > compute(0.5, "auto", 0)


def test_monotonic_in_cosine():
    assert compute(0.9, "auto", 0) > compute(0.4, "auto", 0)


def test_usage_boost_saturates_at_20():
    # beyond 20 usages the boost is clamped, so score stops rising from usage
    assert compute(0.5, "auto", 20) == compute(0.5, "auto", 100)


def test_unknown_confidence_treated_as_auto():
    assert compute(0.5, "", 0) == compute(0.5, "auto", 0)


def test_role_adjustment_is_bounded_and_semantic_gap_wins():
    lens = {"goals": ["risk"], "ranking_weights": {"role": 0.2}}
    relevant = role_adjusted(0.8, "implementation", lens)
    role_match = role_adjusted(0.3, "risk management", lens)
    assert relevant > role_match
    assert 0 <= relevant <= 1
