import asyncio
import threading
import time

import pytest

from app.schemas.research import Claim, DraftReport, MiniBrief, ReportSection, ResearchPlan, Source, SubQuestion
from app.services.orchestrator import ResearchOrchestrator


class FakePlanner:
    def __init__(self, count=4, delay=0): self.count, self.delay = count, delay
    def plan(self, query):
        time.sleep(self.delay)
        return ResearchPlan(original_query=query, sub_questions=[SubQuestion(id=f"sq{i}", question=f"Q{i}", rationale="R") for i in range(self.count)])


class TrackingResearcher:
    active, peak, lock = 0, 0, threading.Lock()
    def __init__(self, fail_id=None, delay=0.03): self.fail_id, self.delay = fail_id, delay
    def investigate(self, question):
        with self.lock:
            type(self).active += 1
            type(self).peak = max(type(self).peak, type(self).active)
        try:
            time.sleep(self.delay)
            if question.id == self.fail_id: raise RuntimeError("research failed")
            return MiniBrief(sub_question_id=question.id, summary="ok", key_findings=["finding"], sources=[Source(url=f"https://{question.id}.test", title="T", snippet="S", search_provider="tavily")])
        finally:
            with self.lock: type(self).active -= 1


class FakeSynthesizer:
    def __init__(self): self.briefs = None
    def synthesize(self, query, briefs):
        self.briefs = briefs
        source = next((source for brief in briefs for source in brief.sources), Source(url="https://fallback.test", title="T", snippet="S", search_provider="tavily"))
        return DraftReport(original_query=query, intro="I", sections=[ReportSection(title="S", claims=[Claim(id="c1", text="F", supporting_source_urls=[source.url])])], conclusion="C", all_sources=[source])


def test_fanout_is_bounded_handles_failure_and_reports_progress():
    TrackingResearcher.active = TrackingResearcher.peak = 0
    synth = FakeSynthesizer()
    stages = []
    orchestrator = ResearchOrchestrator(FakePlanner(5), lambda: TrackingResearcher(fail_id="sq2"), synth, max_concurrent_researchers=2)
    report = asyncio.run(orchestrator.run_pipeline("query", lambda stage, payload: stages.append(stage)))
    assert TrackingResearcher.peak <= 2
    assert len(synth.briefs) == 5
    assert any("could not be researched" in brief.summary for brief in synth.briefs)
    assert report.sections
    assert stages.count("researching") == 5
    assert {"planning", "synthesizing", "done"}.issubset(stages)


def test_broken_progress_callback_does_not_crash_pipeline():
    orchestrator = ResearchOrchestrator(FakePlanner(1), TrackingResearcher, FakeSynthesizer())
    report = asyncio.run(orchestrator.run_pipeline("query", lambda *_: (_ for _ in ()).throw(RuntimeError("broken callback"))))
    assert report.original_query == "query"


def test_pipeline_timeout_fires():
    orchestrator = ResearchOrchestrator(FakePlanner(delay=0.1), TrackingResearcher, FakeSynthesizer(), timeout_seconds=0.01)
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(orchestrator.run_pipeline("query"))
