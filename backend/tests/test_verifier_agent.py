import numpy as np

from app.agents.verifier import VerifierAgent
from app.schemas.research import Claim, DraftReport, ReportSection, Source
from app.services.llm_router import LLMResponse


CONTENT = " ".join(["Cats are domesticated mammals that often live with people."] * 4)


class FakeEmbedder:
    def __init__(self): self.calls = []
    def embed(self, texts):
        self.calls.append(texts)
        return [[1.0, 0.0] for _ in texts]


class FakeRouter:
    def __init__(self): self.calls = []
    def call_llm(self, **kwargs):
        self.calls.append(kwargs)
        return LLMResponse(content='{"verdict":"supported","confidence":0.9,"audit_chunk_text":"Cats are domesticated mammals","reasoning":"The excerpt directly identifies cats as domesticated mammals."}', provider="groq", target="default")


def report(claims):
    source = Source(url="https://cats.test", title="Cats", snippet="Cats are mammals", search_provider="tavily", full_content=CONTENT)
    return DraftReport(original_query="Q", intro="I", sections=[ReportSection(title="Facts", claims=claims)], conclusion="C", all_sources=[source], synthesis_provider="gemini")


def test_supported_claim_has_audit_trail_and_excludes_synthesizer_provider():
    router, embedder = FakeRouter(), FakeEmbedder()
    verified = VerifierAgent(router, embedder).verify_report(report([Claim(id="c1", text="Cats are domesticated mammals.", supporting_source_urls=["https://cats.test"])]), "gemini")
    claim = verified.sections[0].claims[0]
    assert claim.verdict and claim.verdict.verdict == "supported"
    assert claim.verdict.audit_source_url == "https://cats.test"
    assert claim.verdict.audit_chunk_text
    assert router.calls[0]["exclude_provider"] == "gemini"


def test_auto_strip_skips_llm_call():
    router = FakeRouter()
    verified = VerifierAgent(router, FakeEmbedder()).verify_report(report([Claim(id="c1", text="Unsourced", supporting_source_urls=[], unsupported=True)]), "gemini")
    assert router.calls == []
    assert verified.verification_summary["stripped"] == 1
    assert verified.verification_summary["stripped_claims"] == ["Unsourced"]


def test_source_chunks_are_embedded_once_for_multiple_claims():
    embedder = FakeEmbedder()
    claims = [Claim(id="c1", text="Cats are mammals.", supporting_source_urls=["https://cats.test"]), Claim(id="c2", text="Cats live with people.", supporting_source_urls=["https://cats.test"])]
    VerifierAgent(FakeRouter(), embedder).verify_report(report(claims), "gemini")
    assert len(embedder.calls[0]) == 1  # the one unique source's chunk is batched once
    assert len(embedder.calls) == 3  # one chunk batch plus one claim embedding per claim

