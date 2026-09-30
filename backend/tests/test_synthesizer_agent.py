from app.agents.synthesizer import SynthesizerAgent
from app.schemas.research import MiniBrief, Source
from app.services.llm_router import LLMResponse


class FakeRouter:
    def __init__(self, payload): self.payload = payload
    def call_llm(self, **kwargs): return LLMResponse(content=self.payload, provider="gemini", target="key")


def briefs():
    source = Source(url="https://evidence.test", title="Evidence", snippet="Evidence excerpt", search_provider="tavily")
    return [MiniBrief(sub_question_id="sq1", summary="One", key_findings=["One"], sources=[source]), MiniBrief(sub_question_id="sq2", summary="Two", key_findings=["Two"], sources=[source])]


def test_synthesizer_deduplicates_sources_and_assigns_claim_ids():
    payload = '{"intro":"Intro","sections":[{"title":"Theme","claims":[{"text":"Fact","supporting_source_urls":["https://evidence.test"]}]}],"conclusion":"End"}'
    report = SynthesizerAgent(FakeRouter(payload)).synthesize("Query", briefs())
    assert len(report.all_sources) == 1
    assert report.sections[0].claims[0].id == "c1"
    assert report.sections[0].claims[0].unsupported is False


def test_synthesizer_strips_invented_urls_and_flags_claim():
    payload = '{"intro":"Intro","sections":[{"title":"Theme","claims":[{"text":"Fact","supporting_source_urls":["https://invented.test"]}]}],"conclusion":"End"}'
    report = SynthesizerAgent(FakeRouter(payload)).synthesize("Query", briefs())
    claim = report.sections[0].claims[0]
    assert claim.supporting_source_urls == []
    assert claim.unsupported is True

