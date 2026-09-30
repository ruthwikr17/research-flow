from app.agents.researcher import ResearcherAgent
from app.schemas.research import SubQuestion
from app.services.llm_router import LLMResponse
from app.services.search_service import SearchItem, SearchResult


class FakeRouter:
    def __init__(self, payload): self.payload, self.calls = payload, 0
    def call_llm(self, **kwargs):
        self.calls += 1
        return LLMResponse(content=self.payload, provider="groq", target="default")


class FakeSearch:
    def __init__(self, budget=True): self.budget, self.calls = budget, 0
    def has_budget_remaining(self): return self.budget
    def search(self, query, max_results):
        self.calls += 1
        return SearchResult(query, "tavily", [SearchItem("https://example.com", "Evidence", "Cats are mammals.")])


def test_researcher_returns_grounded_minibrief():
    router = FakeRouter('{"summary":"Cats are mammals.","key_findings":["Cats are mammals."],"sources":[{"url":"https://example.com","title":"Evidence","snippet":"Cats are mammals"}]}')
    brief = ResearcherAgent(router, FakeSearch()).investigate(SubQuestion(id="sq1", question="Are cats mammals?", rationale="test"))
    assert brief.sources[0].search_provider == "tavily"
    assert brief.sources[0].full_content == "Cats are mammals."
    assert brief.search_budget_exhausted is False


def test_budget_exhaustion_skips_llm_and_search():
    router, search = FakeRouter("{}"), FakeSearch(budget=False)
    brief = ResearcherAgent(router, search).investigate(SubQuestion(id="sq1", question="Q", rationale="R"))
    assert brief.search_budget_exhausted is True
    assert router.calls == search.calls == 0


def test_invented_url_is_dropped():
    router = FakeRouter('{"summary":"Grounded.","key_findings":[],"sources":[{"url":"https://example.com","title":"Real","snippet":"Cats are mammals"},{"url":"https://invented.test","title":"Fake","snippet":"Fake"}]}')
    brief = ResearcherAgent(router, FakeSearch()).investigate(SubQuestion(id="sq1", question="Q", rationale="R"))
    assert [source.url for source in brief.sources] == ["https://example.com"]
