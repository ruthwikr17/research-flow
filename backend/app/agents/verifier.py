from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np
from pydantic import BaseModel, Field

from app.agents.base import AgentBase
from app.agents.prompts.verifier_prompt import VERIFIER_SYSTEM_PROMPT
from app.schemas.research import Claim, DraftReport
from app.schemas.verification import Chunk, ClaimVerdict, VerifiedReport
from app.services.chunking_service import chunk_text

logger = logging.getLogger(__name__)


class VerifierOutput(BaseModel):
    verdict: str
    confidence: float = Field(ge=0, le=1)
    audit_chunk_text: str | None = None
    reasoning: str


class VerifierAgent(AgentBase):
    def __init__(self, llm_router, embed_service, **kwargs) -> None:
        super().__init__(llm_router, **kwargs)
        self.embed_service = embed_service

    def verify_report(self, report: DraftReport, synthesis_provider: str, on_progress: Callable[[int, int], None] | None = None) -> VerifiedReport:
        chunks_by_url = self._chunks_by_source(report)
        vectors_by_chunk = self._embed_chunks(chunks_by_url)
        verified = report.model_copy(deep=True)
        stripped: list[str] = []
        counts = {"total_claims": 0, "supported": 0, "partially_supported": 0, "unverified": 0, "stripped": 0}
        total_claims = sum(len(section.claims) for section in verified.sections)
        completed_claims = 0

        for section in verified.sections:
            surviving: list[Claim] = []
            for claim in section.claims:
                counts["total_claims"] += 1
                verdict = self._verify_claim(claim, chunks_by_url, vectors_by_chunk, synthesis_provider)
                claim.verdict = verdict
                completed_claims += 1
                if on_progress:
                    try:
                        on_progress(completed_claims, total_claims)
                    except Exception:
                        logger.exception("Verifier progress callback failed")
                if verdict.verdict == "unsupported":
                    counts["stripped"] += 1
                    stripped.append(claim.text)
                else:
                    counts[verdict.verdict] += 1
                    surviving.append(claim)
            section.claims = surviving
            if not surviving:
                logger.info(
                    "Section %r lost all %d claim(s) to verification; clearing narrative.",
                    section.title, counts["stripped"],
                )
                section.narrative = (
                    "No claims for this angle could be verified against retrieved sources."
                )
        return VerifiedReport(**verified.model_dump(), verification_summary={**counts, "stripped_claims": stripped})

    def _chunks_by_source(self, report: DraftReport) -> dict[str, list[Chunk]]:
        chunks: dict[str, list[Chunk]] = {}
        for source in report.all_sources:
            chunks[source.url] = [Chunk(chunk_id=f"{source.url}#{index}", source_url=source.url, text=text) for index, text in enumerate(chunk_text(source.full_content))]
        return chunks

    def _embed_chunks(self, chunks_by_url: dict[str, list[Chunk]]) -> dict[str, np.ndarray]:
        all_chunks = [chunk for chunks in chunks_by_url.values() for chunk in chunks]
        if not all_chunks:
            return {}
        embeddings = self.embed_service.embed([chunk.text for chunk in all_chunks])
        return {chunk.chunk_id: np.asarray(vector) for chunk, vector in zip(all_chunks, embeddings, strict=True)}

    def _verify_claim(self, claim: Claim, chunks_by_url: dict[str, list[Chunk]], vectors_by_chunk: dict[str, np.ndarray], synthesis_provider: str) -> ClaimVerdict:
        if claim.unsupported or not claim.supporting_source_urls:
            return ClaimVerdict(claim_id=claim.id, verdict="unsupported", confidence=0.0, reasoning="No valid source was cited for this claim.")
        candidates = [chunk for url in claim.supporting_source_urls for chunk in chunks_by_url.get(url, [])]
        if not candidates:
            return ClaimVerdict(claim_id=claim.id, verdict="unsupported", confidence=0.0, reasoning="The cited source had no usable text for verification.")
        
        try:
            claim_embedding = np.asarray(self.embed_service.embed([claim.text])[0])
            best = max(candidates, key=lambda chunk: float(np.dot(claim_embedding, vectors_by_chunk[chunk.chunk_id])))
            output = self.call_structured("verifier", [{"role": "system", "content": VERIFIER_SYSTEM_PROMPT}, {"role": "user", "content": f"Claim: {claim.text}\n\nSource excerpt:\n{best.text}"}], VerifierOutput, exclude_provider=synthesis_provider)
            audit_text = output.audit_chunk_text if output.audit_chunk_text and output.audit_chunk_text in best.text else best.text
            if audit_text == best.text and output.audit_chunk_text:
                logger.warning("Verifier supplied an audit quote outside the retrieved chunk; using full retrieved chunk")
            return ClaimVerdict(claim_id=claim.id, verdict=output.verdict, confidence=output.confidence, audit_source_url=best.source_url, audit_chunk_text=audit_text, reasoning=output.reasoning)
        except Exception as exc:
            logger.warning("Verifier LLM error on claim '%s': %s", claim.id, exc)
            return ClaimVerdict(
                claim_id=claim.id,
                verdict="unverified",
                confidence=0.0,
                audit_source_url=candidates[0].source_url if candidates else None,
                reasoning=f"Verification could not complete due to verifier error: {str(exc)}",
                error=str(exc),
            )
