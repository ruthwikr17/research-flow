import numpy as np

from app.agents.verifier import VerifierAgent
from app.schemas.research import Claim, DraftReport, MiniBrief, ReportSection, Source
from app.services.llm_router import LLMResponse
from app.services.orchestrator import ResearchOrchestrator
import asyncio


class KeywordEmbedder:
    """Small deterministic local embedder for an offline adversarial verification test."""
    vocabulary = ("mars", "fourth", "planet", "water", "cats", "mammals")
    def embed(self, texts):
        return [[float(word in text.lower()) for word in self.vocabulary] for text in texts]


class AdversarialRouter:
    def call_llm(self, **kwargs):
        claim = kwargs["messages"][-1]["content"].split("\n", 1)[0].lower()
        if "water" in claim:
            verdict = "unsupported"
            reason = "The excerpt does not establish the planted water claim."
        else:
            verdict = "supported"
            reason = "The excerpt directly supports this claim."
        return LLMResponse(content=f'{{"verdict":"{verdict}","confidence":0.95,"audit_chunk_text":null,"reasoning":"{reason}"}}', provider="groq", target="default")


def test_adversarial_planted_claim_is_stripped_while_supported_claim_survives():
    content = " ".join(["Mars is the fourth planet from the Sun in the Solar System."] * 4)
    source = Source(url="https://mars.test", title="Mars", snippet="Mars is fourth", search_provider="tavily", full_content=content)
    report = DraftReport(original_query="Mars", intro="I", sections=[ReportSection(title="Mars", claims=[Claim(id="c1", text="Mars is the fourth planet from the Sun.", supporting_source_urls=[source.url]), Claim(id="c2", text="Mars has oceans of liquid water today.", supporting_source_urls=[source.url])])], conclusion="C", all_sources=[source], synthesis_provider="gemini")
    verified = VerifierAgent(AdversarialRouter(), KeywordEmbedder()).verify_report(report, "gemini")
    assert [claim.id for claim in verified.sections[0].claims] == ["c1"]
    assert verified.sections[0].claims[0].verdict.audit_chunk_text
    assert verified.verification_summary["stripped_claims"] == ["Mars has oceans of liquid water today."]


def test_orchestrator_runs_verification_before_done():
    class Planner:
        def plan(self, query):
            from app.schemas.research import ResearchPlan, SubQuestion
            return ResearchPlan(original_query=query, sub_questions=[SubQuestion(id="sq1", question="Q", rationale="R")])
    class Researcher:
        def investigate(self, sub_question):
            return MiniBrief(sub_question_id=sub_question.id, summary="brief", key_findings=[], sources=[])
    class Synthesizer:
        def synthesize(self, query, briefs):
            return DraftReport(original_query=query, intro="I", sections=[ReportSection(title="S", claims=[Claim(id="c1", text="Unsourced", supporting_source_urls=[], unsupported=True)])], conclusion="C", all_sources=[], synthesis_provider="gemini")
    events = []
    orchestrator = ResearchOrchestrator(Planner(), Researcher, Synthesizer(), VerifierAgent(AdversarialRouter(), KeywordEmbedder()), max_concurrent_researchers=1)
    verified = asyncio.run(orchestrator.run_pipeline("Q", lambda stage, _: events.append(stage)))
    assert "verifying" in events
    assert verified.verification_summary["stripped"] == 1
