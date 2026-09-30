from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from app.schemas.research import DraftReport, MiniBrief, SubQuestion
from app.schemas.verification import VerifiedReport

logger = logging.getLogger(__name__)
ProgressCallback = Callable[[str, dict[str, Any]], None]


class ResearchOrchestrator:
    def __init__(self, planner: Any, researcher_factory: Callable[[], Any], synthesizer: Any, verifier: Any | None = None, max_concurrent_researchers: int = 4, timeout_seconds: float = 120) -> None:
        self.planner = planner
        self.researcher_factory = researcher_factory
        self.synthesizer = synthesizer
        self.verifier = verifier
        self.max_concurrent_researchers = max_concurrent_researchers
        self.timeout_seconds = timeout_seconds

    async def run_pipeline(self, query: str, on_progress: ProgressCallback | None = None) -> DraftReport | VerifiedReport:
        try:
            return await asyncio.wait_for(self._run(query, on_progress), timeout=self.timeout_seconds)
        except Exception as exc:
            logger.exception("Pipeline failed in run_pipeline: %s", exc)
            self._emit(on_progress, "error", {"message": f"Pipeline failed: {str(exc)}"})
            raise

    async def _run(self, query: str, on_progress: ProgressCallback | None) -> DraftReport | VerifiedReport:
        import time
        start_total = time.time()
        timings: dict[str, float] = {}

        t0 = time.time()
        plan = await asyncio.to_thread(self.planner.plan, query)
        timings["planning"] = round(time.time() - t0, 3)
        self._emit(on_progress, "planning", {"sub_question_count": len(plan.sub_questions)})
        semaphore = asyncio.Semaphore(self.max_concurrent_researchers)
        completed = 0
        seen_urls: set[str] = set()  # shared across all researcher coroutines in this run

        async def research(sub_question: SubQuestion) -> MiniBrief:
            nonlocal completed
            try:
                async with semaphore:
                    brief = await asyncio.to_thread(
                        self.researcher_factory().investigate, sub_question, seen_urls
                    )
            except Exception as exc:
                logger.exception("Researcher failed for %s", sub_question.id)
                brief = MiniBrief(sub_question_id=sub_question.id, summary=f"This angle could not be researched: {exc}", key_findings=[], sources=[])
            completed += 1
            self._emit(on_progress, "researching", {"sub_question_id": sub_question.id, "completed": completed, "remaining": len(plan.sub_questions) - completed})
            return brief

        t0 = time.time()
        briefs = await asyncio.gather(*(research(question) for question in plan.sub_questions))
        timings["researching"] = round(time.time() - t0, 3)

        t0 = time.time()
        self._emit(on_progress, "synthesizing", {"mini_brief_count": len(briefs)})
        report = await asyncio.to_thread(self.synthesizer.synthesize, query, briefs)
        timings["synthesizing"] = round(time.time() - t0, 3)

        if self.verifier is not None:
            t0 = time.time()
            claim_count = sum(len(section.claims) for section in report.sections)
            self._emit(on_progress, "verifying", {"completed": 0, "total": claim_count})
            if not report.synthesis_provider:
                raise RuntimeError("Synthesis provider was not recorded; cross-model verification cannot run")

            def on_verifier_progress(completed: int, total: int) -> None:
                self._emit(on_progress, "verifying", {"completed": completed, "total": total})

            import inspect
            sig = inspect.signature(self.verifier.verify_report)
            if "on_progress" in sig.parameters:
                report = await asyncio.to_thread(self.verifier.verify_report, report, report.synthesis_provider, on_progress=on_verifier_progress)
            else:
                report = await asyncio.to_thread(self.verifier.verify_report, report, report.synthesis_provider)
            timings["verifying"] = round(time.time() - t0, 3)

        timings["total"] = round(time.time() - start_total, 3)
        report.timings = timings
        self._emit(on_progress, "done", {"report": report})
        return report

    @staticmethod
    def _emit(callback: ProgressCallback | None, stage: str, payload: dict[str, Any]) -> None:
        if callback is None:
            return
        try:
            callback(stage, payload)
        except Exception:
            logger.exception("Progress callback failed at stage %s", stage)
