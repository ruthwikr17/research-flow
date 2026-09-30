from app.services.rate_limiter import DailyRateLimiter


def test_rate_limiter_increment_and_cap():
    limiter = DailyRateLimiter(max_queries_per_day=2)
    assert limiter.check_and_increment() is True
    assert limiter.check_and_increment() is True
    assert limiter.check_and_increment() is False

    status = limiter.get_status()
    assert status["queries_today"] == 2
    assert status["max_queries_per_day"] == 2
    assert status["remaining_queries"] == 0
