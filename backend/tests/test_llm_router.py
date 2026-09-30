from app.services.llm_router import LLMRouter, RateLimitError
from app.services.quota_monitor import QuotaMonitor


class FakeAdapter:
    def __init__(self): self.calls = []
    def call(self, provider, target, messages, **kwargs):
        self.calls.append((provider, target))
        if provider == "groq": raise RateLimitError("429")
        return "ok"


def test_primary_429_falls_back_to_secondary():
    adapter = FakeAdapter()
    router = LLMRouter(QuotaMonitor(["g1"]), adapter, sleep=lambda _: None)
    # Planner: primary Groq -> fallback Gemini
    response = router.call_llm("planner", [{"role": "user", "content": "hi"}])
    assert response.provider == "gemini"
    assert adapter.calls == [("groq", "default"), ("gemini", "g1")]


def test_excluded_provider_is_never_called():
    class SuccessfulAdapter:
        def __init__(self): self.calls = []
        def call(self, provider, target, messages, **kwargs):
            self.calls.append((provider, target))
            return "ok"
    adapter = SuccessfulAdapter()
    router = LLMRouter(QuotaMonitor(["g1"]), adapter, sleep=lambda _: None)
    # Verifier: primary Groq -> fallback Gemini; excluding groq calls gemini
    response = router.call_llm("verifier", [{"role": "user", "content": "hi"}], exclude_provider="groq")
    assert response.provider == "gemini"
    assert adapter.calls == [("gemini", "g1")]
