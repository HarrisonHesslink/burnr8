"""Tests for burnr8.tools.competitive — _fmt_share and opportunity analysis."""

from burnr8.tools.competitive import _fmt_share

# ---------------------------------------------------------------------------
# _fmt_share
# ---------------------------------------------------------------------------


class TestFmtShare:
    def test_none_returns_none(self):
        assert _fmt_share(None) is None

    def test_google_ads_sentinel_returns_none(self):
        """Google Ads returns '--' when data volume is too low."""
        assert _fmt_share("--") is None

    def test_float_rounds_to_4_places(self):
        assert _fmt_share(0.1234567) == 0.1235

    def test_one_point_zero(self):
        assert _fmt_share(1.0) == 1.0

    def test_zero(self):
        assert _fmt_share(0.0) == 0.0

    def test_string_number(self):
        assert _fmt_share("0.5") == 0.5

    def test_non_numeric_string_returns_none(self):
        assert _fmt_share("N/A") is None

    def test_bool_coerced(self):
        """bool is a subtype of int in Python — should still work."""
        assert _fmt_share(True) == 1.0
        assert _fmt_share(False) == 0.0
