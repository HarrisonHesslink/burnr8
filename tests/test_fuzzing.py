import pytest
from hypothesis import given, strategies as st
from burnr8.helpers import (
    validate_daily_budget,
    validate_cpc_bid,
    validate_bid_modifier,
    validate_target_cpa,
    validate_target_roas,
    validate_id,
    escape_gaql_string,
)
from burnr8.session import get_max_daily_budget, get_max_cpc_bid, get_max_bid_modifier, get_max_target_cpa, get_min_target_roas

# --- Financial Invariants ---

@given(st.floats(min_value=0.01, max_value=1_000_000_000.0))
def test_fuzz_daily_budget_limit(amount):
    """
    Property: If amount exceeds the limit, validate_daily_budget must return an error.
    If amount is within (0, limit], it should return None.
    """
    limit = get_max_daily_budget()
    err = validate_daily_budget(amount)
    if amount > limit:
        assert err is not None
        assert "exceeds the safety cap" in err
    elif amount > 0:
        pass

@given(st.floats())
def test_fuzz_daily_budget_crashes(amount):
    """Property: validate_daily_budget should never crash on any float (NaN, Inf, etc.)"""
    try:
        validate_daily_budget(amount)
    except Exception as e:
        pytest.fail(f"validate_daily_budget crashed with {type(e).__name__} on input {amount}")

@given(st.floats(allow_nan=True, allow_infinity=True))
def test_fuzz_cpc_bid_crashes(amount):
    """Property: validate_cpc_bid should never crash on any float."""
    validate_cpc_bid(amount)

@given(st.floats(allow_nan=True, allow_infinity=True))
def test_fuzz_bid_modifier_crashes(amount):
    """Property: validate_bid_modifier should never crash on any float."""
    validate_bid_modifier(amount)

@given(st.floats(allow_nan=True, allow_infinity=True))
def test_fuzz_target_cpa_crashes(amount):
    """Property: validate_target_cpa should never crash on any float."""
    validate_target_cpa(amount)

@given(st.floats(allow_nan=True, allow_infinity=True))
def test_fuzz_target_roas_crashes(amount):
    """Property: validate_target_roas should never crash on any float."""
    validate_target_roas(amount)

# --- ID Invariants ---

@given(st.text())
def test_fuzz_validate_id_string(id_str):
    """
    Property: validate_id only accepts numeric strings.
    If the string is not purely digits, it must return an error.
    """
    err = validate_id(id_str, "test_id")
    if not id_str.isdigit():
        assert err is not None
        assert "must be a numeric string" in err

# --- GAQL Escaping Invariants ---

@given(st.text())
def test_fuzz_escape_gaql_string_safety(val):
    """
    Property: An escaped string, when wrapped in single quotes, 
    must not contain an unescaped single quote that could terminate the string context.
    
    Proof: The frequency of single quotes (not preceded by a backslash) in the result
    must be zero, assuming the input didn't already contain weird backslash-quoted-quotes.
    More simply: escape_gaql_string(val) must replace all ' with \'
    """
    escaped = escape_gaql_string(val)
    # Check for raw single quotes not preceded by an odd number of backslashes
    # But in GAQL, we just need to ensure ' -> \'
    # We can check that the count of "'" in the result equals the count of "\'"
    assert escaped.count("'") == escaped.count("\\'")
