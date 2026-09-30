from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Relative to the backend working directory; created automatically on first save.
_DEFAULT_STATE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "data", "usage_state.json"
)


@dataclass
class Usage:
    minute_calls: int = 0
    daily_calls: int = 0
    minute_started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    day_started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_called_at: datetime | None = None
    exhausted_until: datetime | None = None


def _dt_to_str(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt is not None else None


def _str_to_dt(s: str | None) -> datetime | None:
    if s is None:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


class QuotaMonitor:
    """Tracks LLM call quotas with file-backed persistence (Gemini/Groq counters survive restarts).

    Groq: counters are self-corrected from live x-ratelimit-remaining-requests / -tokens headers
    whenever sync_groq_from_headers() is called after a successful Groq response.

    Gemini: counters are incremented per call and persisted to disk so that totals accumulate
    across backend restarts.  No live usage endpoint exists for Gemini.
    """

    def __init__(
        self,
        gemini_project_keys: list[str],
        cooldown_seconds: int = 60,
        state_path: str = _DEFAULT_STATE_PATH,
    ) -> None:
        self.targets = {"gemini": list(gemini_project_keys), "groq": ["default"]}
        self.cooldown = timedelta(seconds=cooldown_seconds)
        self.state_path = os.path.abspath(state_path)
        self.usage: dict[Any, Usage] = {}
        for provider, targets in self.targets.items():
            for target in targets:
                u = Usage()
                self.usage[(provider, target, "default")] = u
                self.usage[(provider, target)] = u

        self._load_state()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _load_state(self) -> None:
        """Load counters from disk.  Silently skips missing or corrupt files."""
        if not os.path.exists(self.state_path):
            return
        try:
            with open(self.state_path, "r") as fh:
                data = json.load(fh)
            entries = data.get("usage", {})
            for raw_key, entry in entries.items():
                parts = raw_key.split("|")
                if len(parts) == 2:
                    key2 = (parts[0], parts[1])
                    key3 = (parts[0], parts[1], "default")
                elif len(parts) == 3:
                    key2 = (parts[0], parts[1])
                    key3 = (parts[0], parts[1], parts[2])
                else:
                    continue

                u = self.usage.get(key3) or self.usage.get(key2)
                if u is None:
                    # Unknown target — skip to avoid polluting usage dict with stale keys
                    continue

                u.daily_calls = entry.get("daily_calls", u.daily_calls)
                u.minute_calls = entry.get("minute_calls", u.minute_calls)
                loaded_day_start = _str_to_dt(entry.get("day_started_at"))
                loaded_min_start = _str_to_dt(entry.get("minute_started_at"))
                if loaded_day_start:
                    u.day_started_at = loaded_day_start
                if loaded_min_start:
                    u.minute_started_at = loaded_min_start
                u.last_called_at = _str_to_dt(entry.get("last_called_at"))
                u.exhausted_until = _str_to_dt(entry.get("exhausted_until"))
            logger.info("QuotaMonitor: loaded persisted state from %s", self.state_path)
        except Exception as exc:
            logger.warning("QuotaMonitor: failed to load state from %s: %s", self.state_path, exc)

    def _save_state(self) -> None:
        """Persist current counters to disk.  Skips on error to avoid disrupting requests."""
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            serialised: dict[str, Any] = {}
            seen_keys: set[tuple] = set()
            for key, u in self.usage.items():
                if not isinstance(key, tuple) or len(key) != 3:
                    continue
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                raw_key = "|".join(str(k) for k in key)
                serialised[raw_key] = {
                    "daily_calls": u.daily_calls,
                    "minute_calls": u.minute_calls,
                    "day_started_at": _dt_to_str(u.day_started_at),
                    "minute_started_at": _dt_to_str(u.minute_started_at),
                    "last_called_at": _dt_to_str(u.last_called_at),
                    "exhausted_until": _dt_to_str(u.exhausted_until),
                }
            with open(self.state_path, "w") as fh:
                json.dump({"usage": serialised}, fh, indent=2)
        except Exception as exc:
            logger.warning("QuotaMonitor: failed to persist state to %s: %s", self.state_path, exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _target(self, provider: str, project_id: str | None) -> str:
        return project_id or "default"

    def _model(self, model: str | None) -> str:
        return model or "default"

    def _refresh(self, usage: Usage, now: datetime) -> None:
        if now - usage.minute_started_at >= timedelta(minutes=1):
            usage.minute_calls, usage.minute_started_at = 0, now
        if now - usage.day_started_at >= timedelta(days=1):
            usage.daily_calls, usage.day_started_at = 0, now
        if usage.exhausted_until and now >= usage.exhausted_until:
            usage.exhausted_until = None

    def _get_or_create_usage(self, provider: str, target: str, model: str) -> Usage:
        key = (provider, target, model)
        if key not in self.usage:
            u = Usage()
            self.usage[key] = u
            if (provider, target) not in self.usage:
                self.usage[(provider, target)] = u
        return self.usage[key]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_call(self, provider: str, project_id: str | None = None, model: str | None = None) -> None:
        target = self._target(provider, project_id)
        m = self._model(model)
        usage = self._get_or_create_usage(provider, target, m)
        now = datetime.now(timezone.utc)
        self._refresh(usage, now)
        usage.minute_calls += 1
        usage.daily_calls += 1
        usage.last_called_at = now
        self._save_state()

    def record_rate_limit_error(
        self,
        provider: str,
        project_id: str | None = None,
        model: str | None = None,
        cooldown_seconds: float | None = None,
    ) -> None:
        target = self._target(provider, project_id)
        m = self._model(model)
        usage = self._get_or_create_usage(provider, target, m)
        cooldown = timedelta(seconds=cooldown_seconds) if cooldown_seconds is not None else self.cooldown
        usage.exhausted_until = datetime.now(timezone.utc) + cooldown
        self._save_state()

    def sync_groq_from_headers(
        self,
        remaining_requests: int | None,
        remaining_tokens: int | None,
        project_id: str | None = None,
        model: str | None = None,
    ) -> None:
        """Self-correct Groq's in-memory counter from live x-ratelimit-remaining-* headers.

        We treat *remaining_requests* as a proxy for how many calls are still permitted in the
        current window.  If the value is 0 we mark the target as exhausted for the standard
        cooldown period.  If it is positive we clear any existing exhausted_until so that routing
        does not continue to block requests that the provider is actually willing to serve.
        """
        target = self._target("groq", project_id)
        m = self._model(model)
        usage = self._get_or_create_usage("groq", target, m)
        now = datetime.now(timezone.utc)
        self._refresh(usage, now)

        if remaining_requests is not None:
            if remaining_requests == 0:
                if usage.exhausted_until is None or usage.exhausted_until <= now:
                    usage.exhausted_until = now + self.cooldown
                    logger.info(
                        "QuotaMonitor: Groq remaining_requests=0; marking exhausted until %s",
                        usage.exhausted_until.isoformat(),
                    )
            else:
                # Provider says we still have capacity — clear any stale cooldown.
                if usage.exhausted_until is not None:
                    logger.info(
                        "QuotaMonitor: Groq remaining_requests=%d; clearing stale exhausted_until",
                        remaining_requests,
                    )
                    usage.exhausted_until = None

        if remaining_tokens is not None and remaining_tokens < 500:
            # Very low token budget — apply a short backoff so we do not exhaust within the window.
            low_tokens_cooldown = timedelta(seconds=10)
            if usage.exhausted_until is None or usage.exhausted_until < now + low_tokens_cooldown:
                usage.exhausted_until = now + low_tokens_cooldown
                logger.info(
                    "QuotaMonitor: Groq remaining_tokens=%d (low); short backoff applied",
                    remaining_tokens,
                )

        self._save_state()

    def get_available_targets(self, provider: str, model: str | None = None) -> list[str]:
        now = datetime.now(timezone.utc)
        available = []
        m = self._model(model)
        for target in self.targets.get(provider, []):
            usage = self._get_or_create_usage(provider, target, m)
            self._refresh(usage, now)
            if usage.exhausted_until is None:
                available.append(target)
        return sorted(
            available,
            key=lambda target: self._get_or_create_usage(provider, target, m).last_called_at
            or datetime.min.replace(tzinfo=timezone.utc),
        )

    def is_provider_available(self, provider: str, model: str | None = None) -> bool:
        return bool(self.get_available_targets(provider, model=model))
