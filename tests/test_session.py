"""Tests for burnr8.session — active account state management."""

import threading

from burnr8.session import get_active_account, resolve_customer_id, set_active_account


class TestSetActiveAccount:
    def test_sets_account(self):
        set_active_account("1234567890")
        assert get_active_account() == "1234567890"

    def test_strips_dashes(self):
        set_active_account("123-456-7890")
        assert get_active_account() == "1234567890"

    def test_overwrites_previous(self):
        set_active_account("1111111111")
        set_active_account("2222222222")
        assert get_active_account() == "2222222222"


class TestGetActiveAccount:
    def test_returns_none_when_unset(self):
        assert get_active_account() is None


class TestResolveCustomerId:
    def test_returns_provided_id(self):
        set_active_account("1111111111")
        assert resolve_customer_id("9999999999") == "9999999999"

    def test_falls_back_to_active(self):
        set_active_account("1111111111")
        assert resolve_customer_id(None) == "1111111111"

    def test_returns_none_when_no_fallback(self):
        assert resolve_customer_id(None) is None

    def test_empty_string_falls_back(self):
        set_active_account("1111111111")
        assert resolve_customer_id("") == "1111111111"


class TestThreadSafety:
    def test_concurrent_set_and_get(self):
        results = []
        barrier = threading.Barrier(2)

        def writer():
            barrier.wait()
            for i in range(100):
                set_active_account(str(i).zfill(10))

        def reader():
            barrier.wait()
            for _ in range(100):
                val = get_active_account()
                if val is not None:
                    results.append(val)

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # All read values should be valid 10-digit strings (no corruption)
        for val in results:
            assert len(val) == 10
            assert val.isdigit()
