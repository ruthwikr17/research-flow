from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel

from app.agents.base import AgentBase
from app.agents.prompts.researcher_prompt import RESEARCHER_SYSTEM_PROMPT
from app.schemas.research import MiniBrief, Source, SubQuestion
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)

MAX_CHARS_PER_RESULT = 6000  # ~1,500 tokens per search result


class KeywordQueryOutput(BaseModel):
    query: str
    """Short, keyword-style search query (≤10 words) derived from the sub-question."""


class ResearcherSourceOutput(BaseModel):
    url: str
    title: str
    snippet: str


class ResearcherOutput(BaseModel):
    summary: str
    key_findings: list[str]
    sources: list[ResearcherSourceOutput]


_KEYWORD_SYSTEM = (
    "You are a search query optimiser. Convert the user's natural-language research "
    "sub-question into a short, keyword-style query of ≤10 words suitable for a web "
    "search engine. Use precise terms. Return ONLY a JSON object: "
    '{"query": "..."}'
)

_REPHRASE_SYSTEM = (
    "You are a search query optimiser. The first search query did not return fresh "
    "sources. Produce an alternative keyword-style query of ≤10 words that approaches "
    "the same sub-question from a different angle — use synonyms, a narrower scope, "
    "or a different authoritative source type. "
    'Return ONLY a JSON object: {"query": "..."}'
)


class ResearcherAgent(AgentBase):
    def __init__(
        self,
        llm_router,
        search_service: SearchService,
        max_search_attempts: int = 3,
        max_results_per_call: int = 5,
        **kwargs: Any,
    ) -> None:
        super().__init__(llm_router, **kwargs)
        self.search_service = search_service
        self.max_search_attempts = max_search_attempts
        self.max_results_per_call = max_results_per_call

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def investigate(
        self,
        sub_question: SubQuestion,
        seen_urls: set[str] | None = None,
    ) -> MiniBrief:
        """Research one sub-question, optionally widening the search if results
        overlap heavily with URLs already cited by sibling researchers."""
        if not self.search_service.has_budget_remaining():
            return MiniBrief(
                sub_question_id=sub_question.id,
                summary="Search budget is exhausted, so no evidence could be gathered for this sub-question.",
                key_findings=[],
                sources=[],
                search_budget_exhausted=True,
            )

        seen_urls = seen_urls or set()
        is_anchor = sub_question.id == "sq_anchor"

        # --- Attempt 1 ---
        keyword_query = self._to_keyword_query(sub_question.question, _KEYWORD_SYSTEM)
        result = self.search_service.search(keyword_query, max_results=self.max_results_per_call)
        returned_urls = [item.url for item in result.results]
        logger.info(
            "[search] sq=%r attempt=1 provider=%r query=%r urls=%s",
            sub_question.id, result.provider, keyword_query, returned_urls,
        )

        # Decide whether a second attempt is warranted:
        #   (a) anchor sub-question: if no direct numeric figure surfaced, widen
        #   (b) any sub-question: if ≥2 returned URLs are already seen by a sibling
        overlap_count = sum(1 for u in returned_urls if u in seen_urls)
        needs_second_attempt = (
            self.max_search_attempts >= 2
            and self.search_service.has_budget_remaining()
            and (is_anchor or overlap_count >= 2)
        )

        if needs_second_attempt:
            logger.info(
                "[search] sq=%r widening (anchor=%s overlap=%d/%d) — firing attempt 2",
                sub_question.id, is_anchor, overlap_count, len(returned_urls),
            )
            rephrase_query = self._to_keyword_query(sub_question.question, _REPHRASE_SYSTEM)
            result2 = self.search_service.search(rephrase_query, max_results=self.max_results_per_call)
            new_urls = [item.url for item in result2.results]
            logger.info(
                "[search] sq=%r attempt=2 provider=%r query=%r urls=%s",
                sub_question.id, result2.provider, rephrase_query, new_urls,
            )

            # Merge: prefer new URLs; fall back to first-attempt results
            existing_urls = {item.url for item in result.results}
            extra = [item for item in result2.results if item.url not in existing_urls]
            result.results = list(result.results) + extra
            logger.info(
                "[search] sq=%r merged: %d total results (%d net-new URLs)",
                sub_question.id, len(result.results), len(extra),
            )

        # Register all returned URLs as seen for downstream researchers
        seen_urls.update(item.url for item in result.results)

        # Build evidence payload for the LLM
        evidence = [
            {
                "url": item.url,
                "title": item.title,
                "content": (item.content or "")[:MAX_CHARS_PER_RESULT],
            }
            for item in result.results
        ]

        output = self.call_structured(
            "researcher",
            [
                {"role": "system", "content": RESEARCHER_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Sub-question id: {sub_question.id}\n"
                        f"Sub-question: {sub_question.question}\n\n"
                        f"Search results:\n{json.dumps(evidence)}"
                    ),
                },
            ],
            ResearcherOutput,
        )

        valid_urls = {item.url for item in result.results}
        content_by_url = {item.url: item.content for item in result.results}
        sources = []
        for source in output.sources:
            if source.url not in valid_urls:
                logger.warning("Researcher invented source URL; dropping it: %s", source.url)
                continue
            sources.append(
                Source(
                    **source.model_dump(),
                    search_provider=result.provider,
                    full_content=content_by_url.get(source.url, ""),
                )
            )

        return MiniBrief(
            sub_question_id=sub_question.id,
            summary=output.summary,
            key_findings=output.key_findings,
            sources=sources,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _to_keyword_query(self, question: str, system_prompt: str) -> str:
        """Ask the LLM to distil a natural-language question into a short keyword query."""
        try:
            kw = self.call_structured(
                "researcher",
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                ],
                KeywordQueryOutput,
            )
            q = kw.query.strip()
            if q:
                return q
        except Exception:
            logger.warning("Keyword query conversion failed; falling back to raw question", exc_info=True)
        return question
