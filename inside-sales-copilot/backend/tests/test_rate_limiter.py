import threading

import pytest

from backend.src.lib.rate_limiter import TokenBucket
from backend.tests.fakes import FakeClock


def make(clock: FakeClock, **kw) -> TokenBucket:
    return TokenBucket(clock=clock.time, sleep=clock.sleep, **kw)


def test_twenty_calls_start_at_least_one_second_apart():
    clock = FakeClock()
    bucket = make(clock)
    starts = []
    for _ in range(20):
        bucket.acquire()
        starts.append(clock.now)
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert len(starts) == 20
    assert min(gaps) >= 1.0 - 1e-6


def test_first_call_waits_one_second_because_the_bucket_starts_empty():
    clock = FakeClock()
    start = clock.now
    make(clock).acquire()
    assert clock.now - start == pytest.approx(1.0)


def test_long_idle_time_does_not_allow_a_burst():
    clock = FakeClock()
    bucket = make(clock)
    bucket.acquire()
    clock.advance(3600)  # an hour of idle time
    t0 = clock.now
    bucket.acquire()  # uses the single stored token, no wait
    assert clock.now == t0
    bucket.acquire()  # the next one must wait a full second
    assert clock.now - t0 == pytest.approx(1.0)


def test_call_after_a_pause_longer_than_a_second_does_not_wait():
    clock = FakeClock()
    bucket = make(clock)
    bucket.acquire()
    clock.advance(1.5)
    t0 = clock.now
    bucket.acquire()
    assert clock.now == t0


def test_partial_refill_waits_only_the_missing_part():
    clock = FakeClock()
    bucket = make(clock)
    bucket.acquire()
    clock.advance(0.25)
    t0 = clock.now
    bucket.acquire()
    assert clock.now - t0 == pytest.approx(0.75)


def test_faster_rate_is_respected():
    clock = FakeClock()
    bucket = make(clock, rate_per_s=2.0)
    starts = []
    for _ in range(5):
        bucket.acquire()
        starts.append(clock.now)
    gaps = [b - a for a, b in zip(starts, starts[1:])]
    assert min(gaps) >= 0.5 - 1e-6


def test_invalid_settings_are_rejected():
    with pytest.raises(ValueError):
        TokenBucket(rate_per_s=0)
    with pytest.raises(ValueError):
        TokenBucket(capacity=0.5)


def test_real_clock_two_calls_are_spaced():
    """One check with the real clock, using a fast bucket so the test stays quick."""
    import time

    bucket = TokenBucket(rate_per_s=20.0)  # 50 ms spacing
    stamps = []
    for _ in range(3):
        bucket.acquire()
        stamps.append(time.monotonic())
    assert stamps[1] - stamps[0] >= 0.045
    assert stamps[2] - stamps[1] >= 0.045


def test_threads_share_one_bucket_and_never_exceed_the_rate():
    """Several threads calling acquire() together still get one token per second in total."""
    lock = threading.Lock()
    clock = FakeClock()
    bucket = make(clock)
    starts: list[float] = []

    def worker():
        for _ in range(5):
            bucket.acquire()
            with lock:
                starts.append(clock.now)

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(starts) == 15
    # total elapsed fake time must cover at least 15 tokens at 1 per second
    assert clock.now - 1000.0 >= 15.0 - 1e-6
