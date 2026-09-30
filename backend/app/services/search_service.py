from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_SEARCH_STATE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "data", "usage_state.json"
)


@dataclass
class SearchItem:
    url: str
    title: str
    content: str
    published_date: str | None = None


@dataclass
class SearchResult:
    query: str
    provider: str
    results: list[SearchItem]


class SearchService:
    """Manages search provider routing and monthly credit budgeting.

    Usage counters are persisted to disk (the same data/usage_state.json used by QuotaMonitor)
    so that they survive backend restarts.  Within a session the counters accumulate normally;
    on load we restore the last-known totals and month marker so we do not over-spend.
    """

    def __init__(
        self,
        tavily_api_key: str,
        exa_api_key: str,
        tavily_monthly_credit_limit: int = 1000,
        exa_monthly_credit_budget: int = 1400,
        client: httpx.Client | None = None,
        state_path: str = _DEFAULT_SEARCH_STATE_PATH,
    ) -> None:
        self.tavily_api_key, self.exa_api_key = tavily_api_key, exa_api_key
        self.limits = {"tavily": tavily_monthly_credit_limit, "exa": exa_monthly_credit_budget}
        self.usage: dict[str, int] = {"tavily": 0, "exa": 0}
        self.month = self._month()
        self.client = client or httpx.Client(timeout=30)
        # state_path=None disables persistence (useful for tests / sandboxed environments).
        self.state_path = os.path.abspath(state_path) if state_path else None
        self._load_state()

    # ------------------------------------------------------------------
    # Calendar helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _month() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def _reset_if_new_month(self) -> None:
        current = self._month()
        if self.month != current:
            self.usage = {"tavily": 0, "exa": 0}
            self.month = current
            self._save_state()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_state(self) -> None:
        """Read persisted search usage from the shared state file."""
        if not self.state_path or not os.path.exists(self.state_path):
            return
        try:
            with open(self.state_path, "r") as fh:
                data = json.load(fh)
            search_data = data.get("search", {})
            persisted_month = search_data.get("month")
            if persisted_month == self._month():
                self.usage["tavily"] = int(search_data.get("tavily", 0))
                self.usage["exa"] = int(search_data.get("exa", 0))
                logger.info(
                    "SearchService: loaded persisted usage — Tavily %d, Exa %d",
                    self.usage["tavily"],
                    self.usage["exa"],
                )
            else:
                logger.info("SearchService: new month detected; starting fresh usage counters")
        except Exception as exc:
            logger.warning("SearchService: failed to load state from %s: %s", self.state_path, exc)

    def _save_state(self) -> None:
        """Write current search usage into the shared state file (merging with existing keys)."""
        if not self.state_path:
            return
        try:
            os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
            existing: dict[str, Any] = {}
            if os.path.exists(self.state_path):
                with open(self.state_path, "r") as fh:
                    try:
                        existing = json.load(fh)
                    except json.JSONDecodeError:
                        existing = {}
            existing["search"] = {
                "month": self.month,
                "tavily": self.usage["tavily"],
                "exa": self.usage["exa"],
            }
            with open(self.state_path, "w") as fh:
                json.dump(existing, fh, indent=2)
        except Exception as exc:
            logger.warning("SearchService: failed to persist state to %s: %s", self.state_path, exc)

    # ------------------------------------------------------------------
    # Provider routing
    # ------------------------------------------------------------------

    def _provider(self) -> str:
        self._reset_if_new_month()
        if self.usage["tavily"] < self.limits["tavily"]:
            return "tavily"
        if self.usage["exa"] < self.limits["exa"]:
            return "exa"
        raise RuntimeError("Search budget exhausted for both Tavily and Exa")

    def has_budget_remaining(self, estimated_calls: int = 1) -> bool:
        self._reset_if_new_month()
        return any(self.usage[name] + estimated_calls <= self.limits[name] for name in self.usage)

    def get_credit_usage(self) -> dict[str, dict[str, int]]:
        self._reset_if_new_month()
        return {name: {"used": self.usage[name], "limit": self.limits[name]} for name in self.usage}

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str, max_results: int = 5) -> SearchResult:
        provider = self._provider()
        raw = self._search_tavily(query, max_results) if provider == "tavily" else self._search_exa(query, max_results)
        self.usage[provider] += 1
        self._save_state()
        return SearchResult(query=query, provider=provider, results=raw)

    def _search_tavily(self, query: str, max_results: int) -> list[SearchItem]:
        response = self.client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": self.tavily_api_key,
                "query": query,
                "max_results": max_results,
                "include_raw_content": True,
            },
        )
        response.raise_for_status()
        return [
            SearchItem(
                url=item["url"],
                title=item.get("title", ""),
                content=item.get("raw_content") or item.get("content", ""),
                published_date=item.get("published_date"),
            )
            for item in response.json().get("results", [])
        ]

    def _search_exa(self, query: str, max_results: int) -> list[SearchItem]:
        response = self.client.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": self.exa_api_key},
            json={"query": query, "numResults": max_results, "contents": {"text": True}},
        )
        response.raise_for_status()
        return [
            SearchItem(
                url=item["url"],
                title=item.get("title", ""),
                content=item.get("text") or item.get("highlights", [""])[0],
                published_date=item.get("publishedDate"),
            )
            for item in response.json().get("results", [])
        ]
