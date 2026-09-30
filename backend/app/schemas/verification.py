from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.schemas.research import ReportSection, Source


class Chunk(BaseModel):
    chunk_id: str
    source_url: str
    text: str


class ClaimVerdict(BaseModel):
    claim_id: str
    verdict: Literal["supported", "partially_supported", "unsupported", "unverified"]
    confidence: float
    audit_source_url: str | None = None
    audit_chunk_text: str | None = None
    reasoning: str
    error: str | None = None


class VerifiedReport(BaseModel):
    """Draft-report shape plus verification results; references resolve in research.py."""
    original_query: str
    intro: str
    sections: list["ReportSection"]
    conclusion: str
    all_sources: list["Source"]
    synthesis_provider: str | None = Field(default=None, exclude=True)
    verification_summary: dict[str, Any]
    timings: dict[str, float] = Field(default_factory=dict)
