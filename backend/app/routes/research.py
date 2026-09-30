import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.planner import PlannerAgent
from app.agents.researcher import ResearcherAgent
from app.schemas.research import MiniBrief, ResearchPlan, SubQuestion
from app.schemas.verification import VerifiedReport

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/research", tags=["research"])
_active_queries: set[str] = set()


class PlanRequest(BaseModel):
    query: str = Field(min_length=1)


class InvestigateRequest(BaseModel):
    sub_question: SubQuestion


@router.post("/plan", response_model=ResearchPlan)
def plan_research(payload: PlanRequest, request: Request) -> ResearchPlan:
    return PlannerAgent(request.app.state.services.llm_router).plan(payload.query)


@router.post("/investigate", response_model=MiniBrief)
def investigate(payload: InvestigateRequest, request: Request) -> MiniBrief:
    services = request.app.state.services
    return ResearcherAgent(services.llm_router, services.search_service, max_searches=services.max_searches_per_researcher).investigate(payload.sub_question)


@router.post("/run", response_model=VerifiedReport)
async def run_research(payload: PlanRequest, request: Request) -> VerifiedReport:
    return await request.app.state.services.orchestrator.run_pipeline(payload.query)


@router.get("/stream")
async def stream_research(request: Request, query: str = Query(..., min_length=1)) -> StreamingResponse:
    query_key = query.strip().lower()
    if query_key in _active_queries:
        async def duplicate_event_generator():
            payload = json.dumps({"stage": "error", "detail": {"message": "A research pipeline is already in progress for this query. Please wait."}})
            yield f"data: {payload}\n\n"
        return StreamingResponse(duplicate_event_generator(), media_type="text/event-stream")

    rate_limiter = request.app.state.services.rate_limiter
    if not rate_limiter.check_and_increment():
        async def rate_limit_event_generator():
            payload = json.dumps({"stage": "error", "detail": {"message": "Daily query limit reached for this demo. Please try again tomorrow UTC midnight."}})
            yield f"data: {payload}\n\n"
        return StreamingResponse(rate_limit_event_generator(), media_type="text/event-stream")

    _active_queries.add(query_key)
    queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()

    def on_progress(stage: str, detail: dict) -> None:
        queue.put_nowait((stage, detail))

    async def event_generator() -> AsyncGenerator[str, None]:
        pipeline_task = asyncio.create_task(
            request.app.state.services.orchestrator.run_pipeline(query, on_progress=on_progress)
        )

        try:
            while not pipeline_task.done() or not queue.empty():
                try:
                    stage, detail = await asyncio.wait_for(queue.get(), timeout=0.2)
                    serialized_detail = detail
                    if stage == "done" and "report" in detail:
                        report_obj = detail["report"]
                        serialized_report = report_obj.model_dump() if hasattr(report_obj, "model_dump") else report_obj
                        logger.info("SSE 'done' event payload report keys: %s", list(serialized_report.keys()) if isinstance(serialized_report, dict) else type(serialized_report))
                        if isinstance(serialized_report, dict):
                            sections = serialized_report.get("sections", [])
                            claims_count = sum(len(s.get("claims", [])) for s in sections)
                            logger.info("SSE 'done' event: sections=%d, total_surviving_claims=%d, verification_summary=%s", len(sections), claims_count, serialized_report.get("verification_summary"))
                        serialized_detail = {"report": serialized_report}
                    payload = json.dumps({"stage": stage, "detail": serialized_detail})
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    continue

            # Ensure any exception in the pipeline task is sent as an error event
            if pipeline_task.done() and not pipeline_task.cancelled():
                exc = pipeline_task.exception()
                if exc:
                    logger.exception("Pipeline task error in stream: %s", exc)
                    payload = json.dumps({"stage": "error", "detail": {"message": f"Pipeline failed: {str(exc)}"}})
                    yield f"data: {payload}\n\n"

        except Exception as exc:
            logger.exception("Error in SSE event generator: %s", exc)
            payload = json.dumps({"stage": "error", "detail": {"message": f"Unexpected server error: {str(exc)}"}})
            yield f"data: {payload}\n\n"
        finally:
            _active_queries.discard(query_key)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

