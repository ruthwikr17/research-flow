from app.agents.planner import PlannerAgent
from app.services.llm_router import LLMResponse


class FakeRouter:
    def __init__(self, responses): self.responses, self.calls = iter(responses), []
    def call_llm(self, **kwargs):
        self.calls.append(kwargs)
        return LLMResponse(content=next(self.responses), provider="gemini", target="key")


def test_planner_returns_normalized_well_formed_plan():
    router = FakeRouter(['{"sub_questions":[{"id":"random","question":"Q1","rationale":"R1"},{"id":"random","question":"Q2","rationale":"R2"},{"id":"","question":"Q3","rationale":"R3"}]}'])
    plan = PlannerAgent(router).plan("Overall query")
    assert plan.original_query == "Overall query"
    assert [item.id for item in plan.sub_questions] == ["sq1", "sq2", "sq3"]


def test_planner_retries_invalid_json_once():
    router = FakeRouter(["not JSON", '{"sub_questions":[{"id":"a","question":"Q","rationale":"R"}]}'])
    plan = PlannerAgent(router).plan("Q")
    assert len(plan.sub_questions) == 1
    assert len(router.calls) == 2
    assert "last response" in router.calls[1]["messages"][-1]["content"]


def test_planner_truncates_over_six_subquestions():
    questions = ",".join(f'{{"id":"{n}","question":"Q{n}","rationale":"R{n}"}}' for n in range(7))
    plan = PlannerAgent(FakeRouter([f'{{"sub_questions":[{questions}]}}'])).plan("Q")
    assert len(plan.sub_questions) == 6


def test_agent_base_normalizes_case_in_keys():
    # Schema expects sub_questions with id, question, rationale
    # Model returns Sub_Questions with Id, Question, Rationale
    router = FakeRouter(['{"Sub_Questions":[{"Id":"sq1","Question":"Test?","Rationale":"Test rationale"}]}'])
    plan = PlannerAgent(router).plan("Q")
    assert len(plan.sub_questions) == 1
    assert plan.sub_questions[0].question == "Test?"
    assert plan.sub_questions[0].rationale == "Test rationale"

