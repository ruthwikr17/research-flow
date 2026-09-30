from datetime import datetime, timezone

from pydantic import BaseModel, Field
from app.schemas.verification import ClaimVerdict, VerifiedReport


class SubQuestion(BaseModel):
    id: str
    question: str
    rationale: str


class ResearchPlan(BaseModel):
    original_query: str
    sub_questions: list[SubQuestion]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Source(BaseModel):
    url: str
    title: str
    snippet: str
    search_provider: str
    full_content: str = ""


class MiniBrief(BaseModel):
    sub_question_id: str
    summary: str
    key_findings: list[str]
    sources: list[Source]
    search_budget_exhausted: bool = False


class Claim(BaseModel):
    id: str
    text: str
    supporting_source_urls: list[str]
    # Internal verifier/evaluation signal; excluded from API output until Phase 3.
    unsupported: bool = Field(default=False, exclude=True)
    verdict: ClaimVerdict | None = None


class ReportSection(BaseModel):
    title: str
    claims: list[Claim]
    narrative: str = ""  # Synthesizer-generated 2-4 sentence interpretive summary


class DraftReport(BaseModel):
    original_query: str
    intro: str
    sections: list[ReportSection]
    conclusion: str
    all_sources: list[Source]
    synthesis_provider: str | None = Field(default=None, exclude=True)
    timings: dict[str, float] = Field(default_factory=dict)




VerifiedReport.model_rebuild(_types_namespace={"ReportSection": ReportSection, "Source": Source})
