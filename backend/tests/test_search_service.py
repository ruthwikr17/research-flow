import httpx

from app.services.search_service import SearchService


def _make_service(tavily_limit: int = 1, exa_limit: int = 2, handler=None):
    """Create a SearchService instance with persistence disabled (state_path=None)."""
    if handler is None:
        def handler(request):
            if "tavily" in str(request.url):
                return httpx.Response(200, json={"results": [{"url": "https://t", "title": "T", "content": "text"}]})
            return httpx.Response(200, json={"results": [{"url": "https://e", "title": "E", "text": "text"}]})
    return SearchService(
        "t", "e",
        tavily_monthly_credit_limit=tavily_limit,
        exa_monthly_credit_budget=exa_limit,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        state_path=None,  # disable persistence so tests are isolated from real disk state
    )


def test_switches_to_exa_and_tracks_each_provider():
    service = _make_service(tavily_limit=1, exa_limit=2)
    assert service.search("first").provider == "tavily"
    assert service.search("second").provider == "exa"
    assert service.get_credit_usage() == {"tavily": {"used": 1, "limit": 1}, "exa": {"used": 1, "limit": 2}}


def test_budget_remains_until_both_providers_exhausted():
    service = _make_service(tavily_limit=1, exa_limit=1)
    assert service.has_budget_remaining()
    service.search("one")
    assert service.has_budget_remaining()
    service.search("two")
    assert not service.has_budget_remaining()
