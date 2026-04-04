"""Tests for burnr8.tools.campaigns — bidding strategy constants."""

from burnr8.tools.campaigns import VALID_BIDDING_STRATEGIES


def test_valid_bidding_strategies_set():
    """Verify all expected bidding strategies are present."""
    assert "MANUAL_CPC" in VALID_BIDDING_STRATEGIES
    assert "MAXIMIZE_CONVERSIONS" in VALID_BIDDING_STRATEGIES
    assert "TARGET_CPA" in VALID_BIDDING_STRATEGIES
    assert "TARGET_ROAS" in VALID_BIDDING_STRATEGIES
    assert "MAXIMIZE_CLICKS" in VALID_BIDDING_STRATEGIES
    assert len(VALID_BIDDING_STRATEGIES) == 9


def test_invalid_strategy_not_in_set():
    """Verify invalid strategies are not in the set."""
    assert "INVALID" not in VALID_BIDDING_STRATEGIES
    assert "AUTO" not in VALID_BIDDING_STRATEGIES


def test_all_strategies_are_uppercase():
    """All strategy names should be uppercase with underscores."""
    for strategy in VALID_BIDDING_STRATEGIES:
        assert strategy == strategy.upper(), f"Strategy '{strategy}' is not uppercase"
        assert " " not in strategy, f"Strategy '{strategy}' contains spaces"


def test_complete_strategy_list():
    """Verify the exact set of strategies."""
    expected = {
        "MANUAL_CPC", "MANUAL_CPM", "MAXIMIZE_CLICKS", "MAXIMIZE_CONVERSIONS",
        "MAXIMIZE_CONVERSION_VALUE", "TARGET_CPA", "TARGET_ROAS",
        "TARGET_IMPRESSION_SHARE", "TARGET_SPEND",
    }
    assert expected == VALID_BIDDING_STRATEGIES


def test_strategies_is_a_set():
    """VALID_BIDDING_STRATEGIES should be a set for O(1) lookup."""
    assert isinstance(VALID_BIDDING_STRATEGIES, set)
