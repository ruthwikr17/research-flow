from __future__ import annotations

import json
import logging
import time
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.services.llm_router import LLMRouter

logger = logging.getLogger(__name__)
SchemaT = TypeVar("SchemaT", bound=BaseModel)


class AgentBase:
    def __init__(self, llm_router: LLMRouter, max_retries: int = 2, timeout_seconds: float = 30) -> None:
        self.llm_router = llm_router
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds
        self.last_raw_response: str | None = None
        self.last_parsed_response: BaseModel | None = None
        self.last_response_provider: str | None = None

    def call_structured(self, role: str, messages: list[dict[str, Any]], schema: type[SchemaT], **kwargs: Any) -> SchemaT:
        """Call an LLM with a JSON contract and one-or-more bounded correction attempts."""
        started = time.monotonic()
        attempt_messages = list(messages)
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            if time.monotonic() - started > self.timeout_seconds:
                raise TimeoutError(f"{role} agent exceeded {self.timeout_seconds}s budget")
            response = self.llm_router.call_llm(role=role, messages=attempt_messages, **kwargs)
            if time.monotonic() - started > self.timeout_seconds:
                raise TimeoutError(f"{role} agent exceeded {self.timeout_seconds}s budget")
            raw = response.content
            self.last_raw_response = raw
            self.last_response_provider = response.provider
            cleaned_json = self._clean_json(raw)
            try:
                data = json.loads(cleaned_json)
                normalized_data = self._normalize_keys(data)
                parsed = schema.model_validate(normalized_data)
                self.last_parsed_response = parsed
                logger.debug("%s raw response: %s; parsed: %s", role, raw, parsed.model_dump())
                return parsed
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                logger.warning("%s returned invalid structured output (attempt %s): %s", role, attempt + 1, raw)
                attempt_messages = [*attempt_messages, {"role": "assistant", "content": raw}, {"role": "user", "content": f"Your last response was not valid JSON matching the required schema ({exc}). Return only corrected JSON."}]
        raise ValueError(f"{role} did not return valid JSON after {self.max_retries} attempts") from last_error

    @staticmethod
    def _normalize_keys(obj: Any) -> Any:
        """Recursively lowercase all dict keys to handle model casing variations (e.g. Snippet vs snippet)."""
        if isinstance(obj, dict):
            return {k.lower() if isinstance(k, str) else k: AgentBase._normalize_keys(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [AgentBase._normalize_keys(item) for item in obj]
        return obj

    @staticmethod
    def _clean_json(text: str) -> str:
        s = text.strip()
        if s.startswith("```"):
            lines = s.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            s = "\n".join(lines).strip()
        # Find outermost JSON object or array if still not clean
        if not (s.startswith("{") or s.startswith("[")):
            start_brace = s.find("{")
            start_bracket = s.find("[")
            indices = [i for i in (start_brace, start_bracket) if i != -1]
            if indices:
                start = min(indices)
                end = max(s.rfind("}"), s.rfind("]"))
                if end > start:
                    s = s[start:end + 1].strip()
        return s
