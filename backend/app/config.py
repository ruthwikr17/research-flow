from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Required credentials intentionally fail at app startup."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    groq_api_key: str = Field(min_length=1)
    gemini_project_keys: str | list[str]
    gemini_models: str | list[str] = "gemini-3.5-flash-lite,gemini-3.1-flash-lite"
    groq_model_planner: str = "openai/gpt-oss-20b"
    groq_model_verifier: str = "openai/gpt-oss-120b"
    groq_model_fallback: str = "openai/gpt-oss-20b"
    tavily_api_key: str = Field(min_length=1)
    exa_api_key: str = Field(min_length=1)
    tavily_monthly_credit_limit: int = 1000
    exa_monthly_credit_budget: int = 1400
    max_concurrent_researchers: int = 4
    # Number of distinct search() calls allowed per researcher (widening attempts)
    max_search_attempts_per_researcher: int = 3
    # Number of results fetched per individual search() call
    max_results_per_search_call: int = 5
    pipeline_timeout_seconds: int = 120
    max_queries_per_day: int = 30
    frontend_origins: str = "http://localhost:3000"

    @field_validator("gemini_models", mode="after")
    @classmethod
    def split_gemini_models(cls, value: str | list[str]) -> list[str]:
        models = value.split(",") if isinstance(value, str) else value
        cleaned = [m.strip() for m in models if m.strip()]
        return cleaned or ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]

    @field_validator("gemini_project_keys", mode="after")
    @classmethod
    def split_gemini_keys(cls, value: str | list[str]) -> list[str]:
        keys = value.split(",") if isinstance(value, str) else value
        cleaned = [key.strip() for key in keys if key.strip()]
        if not cleaned:
            raise ValueError("GEMINI_PROJECT_KEYS must contain at least one API key")
        return cleaned

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.frontend_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
