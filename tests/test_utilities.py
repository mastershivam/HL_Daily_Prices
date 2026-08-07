import pytest

from utilities import with_retries


def test_with_retries_returns_result_on_success():
    assert with_retries(lambda: 42) == 42


def test_with_retries_retries_transient_failures_then_succeeds(monkeypatch):
    monkeypatch.setattr("utilities.time.sleep", lambda _: None)
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "ok"

    assert with_retries(flaky, retries=3, exceptions=(ValueError,)) == "ok"
    assert calls["n"] == 3


def test_with_retries_raises_last_exception_after_exhausting_attempts(monkeypatch):
    monkeypatch.setattr("utilities.time.sleep", lambda _: None)

    def always_fails():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        with_retries(always_fails, retries=2, exceptions=(ValueError,))


def test_with_retries_does_not_retry_unlisted_exceptions(monkeypatch):
    monkeypatch.setattr("utilities.time.sleep", lambda _: None)
    calls = {"n": 0}

    def raises_type_error():
        calls["n"] += 1
        raise TypeError("not retried")

    with pytest.raises(TypeError):
        with_retries(raises_type_error, retries=3, exceptions=(ValueError,))
    assert calls["n"] == 1
