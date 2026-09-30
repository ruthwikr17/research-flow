import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Protocol

from app.services.quota_monitor import QuotaMonitor

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    content: str
    provider: str
    target: str


class RateLimitError(Exception):
    """Provider-neutral 429 used by the adapter boundary."""
    def __init__(self, message: str, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ModelNotFoundError(Exception):
    """Fatal error when requested model ID does not exist on provider."""


class LLMAdapter(Protocol):
    def call(self, provider: str, target: str, messages: list[dict[str, Any]], **kwargs: Any) -> str: ...


class SDKAdapter:
    """Small SDK boundary so routing tests never invoke a remote model."""
    def __init__(self, groq_api_key: str) -> None:
        self.groq_api_key = groq_api_key

    def call(self, provider: str, target: str, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        try:
            if provider == "groq":
                from groq import Groq
                client = Groq(api_key=self.groq_api_key)
                model = kwargs.pop("model", "openai/gpt-oss-20b")
                response = client.chat.completions.with_raw_response.create(
                    messages=messages,
                    model=model,
                    **kwargs
                )
                headers = response.headers

                # Parse live rate-limit headers for quota self-correction.
                remaining_requests: int | None = None
                remaining_tokens: int | None = None
                try:
                    rr = headers.get("x-ratelimit-remaining-requests")
                    if rr is not None:
                        remaining_requests = int(rr)
                    rt = headers.get("x-ratelimit-remaining-tokens")
                    if rt is not None:
                        remaining_tokens = int(rt)
                except (ValueError, TypeError):
                    pass

                # Stash parsed header values on the adapter so LLMRouter can forward them.
                self._last_groq_remaining_requests = remaining_requests
                self._last_groq_remaining_tokens = remaining_tokens

                if remaining_tokens is not None and remaining_tokens < 2000:
                    logger.warning("Groq low remaining tokens (%d); applying 2s backoff", remaining_tokens)
                    time.sleep(2.0)

                parsed = response.parse()
                return parsed.choices[0].message.content or ""

            from google import genai
            client = genai.Client(api_key=target)
            prompt = "\n".join(f"{item.get('role', 'user')}: {item.get('content', '')}" for item in messages)
            model = kwargs.pop("model", "gemini-3.5-flash-lite")
            result = client.models.generate_content(model=model, contents=prompt)
            return result.text or ""
        except Exception as exc:
            msg = str(exc).lower()
            status_code = getattr(exc, "status_code", None)
            if status_code == 404 or "not found" in msg or "model_not_found" in msg or "does not exist" in msg:
                raise ModelNotFoundError(f"Model not found on {provider}: {exc}") from exc
            if status_code == 429 or "429" in msg or "resource_exhausted" in msg:
                # Check for groq retry headers if available
                retry_after = None
                resp = getattr(exc, "response", None)
                if resp and hasattr(resp, "headers"):
                    val = resp.headers.get("retry-after")
                    if val:
                        try:
                            retry_after = float(val)
                        except ValueError:
                            pass
                raise RateLimitError(str(exc), retry_after_seconds=retry_after) from exc
            raise


class LLMRouter:
    """Routes LLM requests according to role preferences, env-configured models, and quota tracking."""

    def __init__(
        self,
        quota_monitor: QuotaMonitor,
        adapter: LLMAdapter,
        models_config: dict[str, Any] | None = None,
        max_retries: int = 3,
        sleep=time.sleep
    ) -> None:
        self.quota_monitor, self.adapter = quota_monitor, adapter
        self.max_retries, self.sleep = max_retries, sleep
        self.models_config = models_config or {}

    def _get_role_targets(self, role: str) -> list[tuple[str, str]]:
        """Return list of (provider, model) pairs according to project spec:
        Planner: Groq gpt-oss-20b -> Gemini Flash-Lite
        Researcher: Gemini 3.5-flash-lite -> Groq
        Synthesizer: Gemini 3.5-flash-lite -> Gemini 3.1-flash-lite
        Verifier: Groq gpt-oss-120b -> Gemini Flash-Lite
        """
        gemini_models = self.models_config.get("gemini_models", ["gemini-3.5-flash-lite", "gemini-3.1-flash-lite"])
        gemini_primary = gemini_models[0] if gemini_models else "gemini-3.5-flash-lite"
        gemini_fallback = gemini_models[1] if len(gemini_models) > 1 else gemini_primary

        groq_planner = self.models_config.get("groq_model_planner", "openai/gpt-oss-20b")
        groq_verifier = self.models_config.get("groq_model_verifier", "openai/gpt-oss-120b")
        groq_fallback = self.models_config.get("groq_model_fallback", "openai/gpt-oss-20b")

        if role == "planner":
            return [("groq", groq_planner), ("gemini", gemini_primary)]
        if role == "researcher":
            return [("gemini", gemini_primary), ("groq", groq_fallback)]
        if role == "synthesizer":
            return [("gemini", gemini_primary), ("gemini", gemini_fallback)]
        if role == "verifier":
            return [("groq", groq_verifier), ("gemini", gemini_primary)]
        return [("gemini", gemini_primary), ("groq", groq_fallback)]

    def call_llm(self, role: str, messages: list[dict[str, Any]], **kwargs: Any) -> LLMResponse:
        exclude_provider = kwargs.pop("exclude_provider", None)
        explicit_model = kwargs.pop("model", None)
        role_targets = self._get_role_targets(role)

        filtered_targets = [
            (provider, explicit_model or model)
            for provider, model in role_targets
            if provider != exclude_provider
        ]

        last_error: Exception | None = None
        logger.info("Routing %s request across provider/model pairs: %s", role, filtered_targets)

        for provider, model in filtered_targets:
            available_projects = self.quota_monitor.get_available_targets(provider, model=model)
            logger.info("Provider '%s' (model: %s) has %d available project target(s)", provider, model, len(available_projects))

            for project_target in available_projects:
                for attempt in range(self.max_retries):
                    try:
                        content = self.adapter.call(provider, project_target, messages, model=model, **kwargs)
                        self.quota_monitor.record_call(provider, project_target, model=model)
                        # Self-correct Groq quota from live response headers.
                        if provider == "groq":
                            rr = getattr(self.adapter, "_last_groq_remaining_requests", None)
                            rt = getattr(self.adapter, "_last_groq_remaining_tokens", None)
                            self.quota_monitor.sync_groq_from_headers(
                                remaining_requests=rr,
                                remaining_tokens=rt,
                                project_id=project_target,
                                model=model,
                            )
                        return LLMResponse(content=content, provider=provider, target=project_target)
                    except ModelNotFoundError as exc:
                        # Fail-fast on model not found instead of retrying
                        logger.error("Fail fast: %s on target '%s'", exc, project_target)
                        raise
                    except RateLimitError as exc:
                        logger.warning("Rate limit hit on %s target '%s' (model: %s): %s", provider, project_target, model, exc)
                        cooldown = exc.retry_after_seconds or 60.0
                        self.quota_monitor.record_rate_limit_error(provider, project_target, model=model, cooldown_seconds=cooldown)
                        last_error = exc
                        break
                    except Exception as exc:
                        msg = str(exc).lower()
                        if "not found" in msg or "model_not_found" in msg or "does not exist" in msg:
                            logger.error("Fail fast: model not found: %s", exc)
                            raise ModelNotFoundError(f"Model '{model}' not found on {provider}: {exc}") from exc
                        logger.warning("Error on %s target '%s' (attempt %d): %s", provider, project_target, attempt + 1, exc)
                        last_error = exc
                        if attempt == self.max_retries - 1:
                            break
                        self.sleep(min(64, 2**attempt) + random.uniform(0, 0.5))

        raise RuntimeError(f"No LLM target succeeded: {last_error}") from last_error

