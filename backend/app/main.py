from contextlib import asynccontextmanager
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routes.health import router as health_router
from app.routes.research import router as research_router
from app.routes.usage import router as usage_router
from app.services.embed_service import EmbedService
from app.services.llm_router import LLMRouter, SDKAdapter
from app.services.quota_monitor import QuotaMonitor
from app.services.rate_limiter import DailyRateLimiter
from app.services.search_service import SearchService
from app.services.orchestrator import ResearchOrchestrator
from app.agents.planner import PlannerAgent
from app.agents.researcher import ResearcherAgent
from app.agents.synthesizer import SynthesizerAgent
from app.agents.verifier import VerifierAgent


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()  # validates all required credentials before serving requests
    quota_monitor = QuotaMonitor(settings.gemini_project_keys)
    models_config = {
        "gemini_models": settings.gemini_models,
        "groq_model_planner": settings.groq_model_planner,
        "groq_model_verifier": settings.groq_model_verifier,
        "groq_model_fallback": settings.groq_model_fallback,
    }
    llm_router = LLMRouter(quota_monitor, SDKAdapter(settings.groq_api_key), models_config=models_config)
    search_service = SearchService(settings.tavily_api_key, settings.exa_api_key, settings.tavily_monthly_credit_limit, settings.exa_monthly_credit_budget)
    embed_service = EmbedService()
    rate_limiter = DailyRateLimiter(max_queries_per_day=settings.max_queries_per_day)
    app.state.services = SimpleNamespace(
        quota_monitor=quota_monitor,
        search_service=search_service,
        embed_service=embed_service,
        llm_router=llm_router,
        rate_limiter=rate_limiter,
        max_search_attempts_per_researcher=settings.max_search_attempts_per_researcher,
        orchestrator=ResearchOrchestrator(
            PlannerAgent(llm_router),
        lambda: ResearcherAgent(
                llm_router, search_service,
                max_search_attempts=settings.max_search_attempts_per_researcher,
                max_results_per_call=settings.max_results_per_search_call,
            ),
            SynthesizerAgent(llm_router),
            VerifierAgent(llm_router, embed_service),
            max_concurrent_researchers=settings.max_concurrent_researchers,
            timeout_seconds=settings.pipeline_timeout_seconds,
            max_concurrent_pipelines=settings.max_concurrent_pipelines,
        ),
    )
    yield


settings = get_settings()
app = FastAPI(title="ResearchFlow", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(health_router)
app.include_router(research_router)
app.include_router(usage_router)
