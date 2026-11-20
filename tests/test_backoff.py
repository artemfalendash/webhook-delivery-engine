"""
Tests for retry delays (app/core/backoff.py).

The delay is random (jitter), so tests can't check one exact number.
Instead we check the LIMITS: the highest possible wait for each attempt.
"""
import pytest

from app.core import backoff
from app.core.backoff import get_retry_delay


@pytest.fixture
def always_max_jitter(monkeypatch):
    """Make the 'random' pick always choose the highest allowed wait."""
    monkeypatch.setattr(backoff.random, "uniform", lambda low, high: high)


@pytest.mark.parametrize(
    "attempt, max_wait",
    [
        (1, 5),      # 5s
        (2, 25),     # 25s
        (3, 125),    # ~2 min
        (4, 625),    # ~10 min
        (5, 3125),   # ~52 min
        (6, 3600),   # capped at 1 hour
        (20, 3600),  # still capped, no matter how many attempts
    ],
)
def test_max_wait_grows_per_attempt_and_caps_at_one_hour(always_max_jitter, attempt, max_wait):
    assert get_retry_delay(attempt) == max_wait


def test_delay_is_never_negative_or_above_the_limit():
    for attempt in range(1, 8):
        for _ in range(200):
            delay = get_retry_delay(attempt)
            assert 0 <= delay <= min(3600, 5 * 5 ** (attempt - 1))


def test_delays_are_randomized_not_identical():
    """Jitter: 50 failed jobs must NOT all retry at the same moment."""
    delays = {get_retry_delay(3) for _ in range(50)}
    assert len(delays) > 1
