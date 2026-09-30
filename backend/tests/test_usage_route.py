import os
os.environ["GROQ_API_KEY"] = "mock_groq_key"
os.environ["GEMINI_PROJECT_KEYS"] = '["mock_gemini_key"]'
os.environ["TAVILY_API_KEY"] = "mock_tavily_key"
os.environ["EXA_API_KEY"] = "mock_exa_key"

from fastapi.testclient import TestClient
from app.main import app


def test_get_usage_endpoint():
    with TestClient(app) as client:
        response = client.get("/usage")
        assert response.status_code == 200
        data = response.json()
        assert "search" in data
        assert "llm" in data
        assert "rate_limit" in data
        assert "queries_today" in data["rate_limit"]
