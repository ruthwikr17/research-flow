from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from app.agents.base import AgentBase
from app.agents.prompts.planner_prompt import PLANNER_SYSTEM_PROMPT
from app.schemas.research import ResearchPlan, SubQuestion

logger = logging.getLogger(__name__)


class PlannerOutput(BaseModel):
    sub_questions: list[SubQuestion]


class PlannerAgent(AgentBase):
    def plan(self, query: str) -> ResearchPlan:
        output = self.call_structured("planner", [{"role": "system", "content": PLANNER_SYSTEM_PROMPT}, {"role": "user", "content": f"Research query: {query}"}], PlannerOutput)
        sub_questions = output.sub_questions[:6]
        if len(output.sub_questions) > 6:
            logger.warning("Planner returned %d sub-questions; truncating to 6", len(output.sub_questions))
        if not sub_questions:
            raise ValueError("Planner returned no sub-questions")
        normalized = [SubQuestion(id=f"sq{index}", question=item.question, rationale=item.rationale) for index, item in enumerate(sub_questions, start=1)]
        return ResearchPlan(original_query=query, sub_questions=normalized)

