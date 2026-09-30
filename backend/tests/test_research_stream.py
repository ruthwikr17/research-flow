import os
os.environ["GROQ_API_KEY"] = "mock_groq_key"
os.environ["GEMINI_PROJECT_KEYS"] = '["mock_gemini_key"]'
os.environ["TAVILY_API_KEY"] = "mock_tavily_key"
os.environ["EXA_API_KEY"] = "mock_exa_key"

from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.rate_limiter import DailyRateLimiter


def test_research_stream_success():
    async def mock_run_pipeline(query, on_progress=None):
        if on_progress:
            on_progress("planning", {"sub_question_count": 3})
            on_progress("researching", {"completed": 1, "remaining": 2})
            on_progress("synthesizing", {"mini_brief_count": 3})
            on_progress("verifying", {"completed": 1, "total": 2})
            on_progress("done", {"report": {"title": "Test Report", "sections": []}})
        return MagicMock()

    with TestClient(app) as client:
        app.state.services.orchestrator.run_pipeline = mock_run_pipeline
        app.state.services.rate_limiter = DailyRateLimiter(max_queries_per_day=10)

        response = client.get("/research/stream?query=quantum+computing")
        assert response.status_code == 200
        content = response.text
        assert "data: {" in content
        assert '"stage": "planning"' in content
        assert '"stage": "researching"' in content
        assert '"stage": "synthesizing"' in content
        assert '"stage": "verifying"' in content
        assert '"stage": "done"' in content


def test_research_stream_rate_limited():
    with TestClient(app) as client:
        limiter = DailyRateLimiter(max_queries_per_day=1)
        limiter.check_and_increment()  # exhaust limit
        app.state.services.rate_limiter = limiter

        response = client.get("/research/stream?query=quantum+computing")
        assert response.status_code == 200
        content = response.text
        assert '"stage": "error"' in content
        assert "Daily query limit reached" in content
