from __future__ import annotations

from datetime import datetime, timezone
import threading


class DailyRateLimiter:
    """Simple in-memory daily rate limiter.

    Note: Resets on application restart and at UTC midnight. Known v1 limitation.
    """

    def __init__(self, max_queries_per_day: int = 30) -> None:
        self.max_queries_per_day = max_queries_per_day
        self.queries_today = 0
        self.current_date = datetime.now(timezone.utc).date()
        self._lock = threading.Lock()

    def _check_reset(self) -> None:
        today = datetime.now(timezone.utc).date()
        if today != self.current_date:
            self.current_date = today
            self.queries_today = 0

    def check_and_increment(self) -> bool:
        """Returns True if within limit (and increments count), False if limit reached."""
        with self._lock:
            self._check_reset()
            if self.queries_today >= self.max_queries_per_day:
                return False
            self.queries_today += 1
            return True

    def get_status(self) -> dict[str, int]:
        """Return current rate limiter status."""
        with self._lock:
            self._check_reset()
            return {
                "queries_today": self.queries_today,
                "max_queries_per_day": self.max_queries_per_day,
                "remaining_queries": max(0, self.max_queries_per_day - self.queries_today),
            }
