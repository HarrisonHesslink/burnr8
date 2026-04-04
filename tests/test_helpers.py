"""Tests for burnr8.helpers — conversion functions and validators."""


from burnr8.helpers import (
    dollars_to_micros,
    micros_to_dollars,
    validate_date_range,
    validate_id,
    validate_status,
)

# ---------------------------------------------------------------------------
# micros_to_dollars
# ---------------------------------------------------------------------------

class TestMicrosToDollars:
    def test_one_million_micros(self):
        assert micros_to_dollars(1_000_000) == 1.0

    def test_zero(self):
        assert micros_to_dollars(0) == 0.0

    def test_fractional_dollars(self):
        assert micros_to_dollars(1_500_000) == 1.5

    def test_sub_dollar_precision(self):
        assert micros_to_dollars(999_999) == 0.999999


# ---------------------------------------------------------------------------
# dollars_to_micros
# ---------------------------------------------------------------------------

class TestDollarsToMicros:
    def test_one_dollar(self):
        assert dollars_to_micros(1.0) == 1_000_000

    def test_zero(self):
        assert dollars_to_micros(0.0) == 0

    def test_fractional_dollars(self):
        assert dollars_to_micros(1.5) == 1_500_000

    def test_rounding(self):
        # 1.999999 * 1_000_000 = 1_999_999.0 — round() keeps it at 1_999_999
        assert dollars_to_micros(1.999999) == 1_999_999

    def test_whole_dollar_as_float(self):
        assert dollars_to_micros(5.00) == 5_000_000


# ---------------------------------------------------------------------------
# validate_id
# ---------------------------------------------------------------------------

class TestValidateId:
    def test_valid_numeric(self):
        assert validate_id("1234567890", "customer_id") is None

    def test_dashes_rejected(self):
        err = validate_id("123-456-7890", "customer_id")
        assert err is not None
        assert "customer_id" in err

    def test_alpha_rejected(self):
        err = validate_id("abc", "campaign_id")
        assert err is not None
        assert "campaign_id" in err

    def test_empty_string_rejected(self):
        err = validate_id("", "ad_group_id")
        assert err is not None

    def test_zero_is_valid(self):
        assert validate_id("0", "id") is None


# ---------------------------------------------------------------------------
# validate_status
# ---------------------------------------------------------------------------

class TestValidateStatus:
    def test_enabled(self):
        assert validate_status("ENABLED") is None

    def test_paused(self):
        assert validate_status("PAUSED") is None

    def test_removed(self):
        assert validate_status("REMOVED") is None

    def test_case_insensitive(self):
        assert validate_status("enabled") is None

    def test_invalid_status(self):
        err = validate_status("DELETED")
        assert err is not None
        assert "DELETED" in err

    def test_empty_string(self):
        err = validate_status("")
        assert err is not None


# ---------------------------------------------------------------------------
# validate_date_range
# ---------------------------------------------------------------------------

class TestValidateDateRange:
    def test_last_30_days(self):
        assert validate_date_range("LAST_30_DAYS") is None

    def test_last_7_days(self):
        assert validate_date_range("LAST_7_DAYS") is None

    def test_today(self):
        assert validate_date_range("TODAY") is None

    def test_case_insensitive(self):
        assert validate_date_range("last_30_days") is None

    def test_all_time_invalid(self):
        err = validate_date_range("ALL_TIME")
        assert err is not None
        assert "ALL_TIME" in err

    def test_invalid_string(self):
        err = validate_date_range("INVALID")
        assert err is not None

    def test_empty_string(self):
        err = validate_date_range("")
        assert err is not None
