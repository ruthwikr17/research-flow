from __future__ import annotations

import json
import logging

from pydantic import BaseModel

from app.agents.base import AgentBase
from app.agents.prompts.synthesizer_prompt import SYNTHESIZER_SYSTEM_PROMPT
from app.schemas.research import Claim, DraftReport, MiniBrief, ReportSection, Source

logger = logging.getLogger(__name__)


class ClaimOutput(BaseModel):
    text: str
    supporting_source_urls: list[str]


class SectionOutput(BaseModel):
    title: str
    claims: list[ClaimOutput]
    narrative: str = ""


class SynthesizerOutput(BaseModel):
    intro: str
    sections: list[SectionOutput]
    conclusion: str


class SynthesizerAgent(AgentBase):
    def synthesize(self, original_query: str, mini_briefs: list[MiniBrief]) -> DraftReport:
        all_sources = self._deduplicate_sources(mini_briefs)
        output = self.call_structured("synthesizer", [{"role": "system", "content": SYNTHESIZER_SYSTEM_PROMPT}, {"role": "user", "content": f"Original query: {original_query}\n\nMini-briefs:\n{json.dumps([brief.model_dump() for brief in mini_briefs])}"}], SynthesizerOutput)
        valid_urls = {source.url for source in all_sources}
        claim_number = 0
        sections: list[ReportSection] = []
        for section in output.sections:
            claims = []
            for item in section.claims:
                claim_number += 1
                urls = []
                for url in item.supporting_source_urls:
                    if url not in valid_urls:
                        logger.warning("Synthesizer invented source URL; dropping it: %s", url)
                    else:
                        urls.append(url)
                claims.append(Claim(id=f"c{claim_number}", text=item.text, supporting_source_urls=urls, unsupported=not urls))
            sections.append(ReportSection(title=section.title, claims=claims, narrative=section.narrative))
        return DraftReport(original_query=original_query, intro=output.intro, sections=sections, conclusion=output.conclusion, all_sources=all_sources, synthesis_provider=self.last_response_provider)

    @staticmethod
    def _deduplicate_sources(mini_briefs: list[MiniBrief]) -> list[Source]:
        by_url: dict[str, Source] = {}
        for brief in mini_briefs:
            for source in brief.sources:
                by_url.setdefault(source.url, source)
        return list(by_url.values())
