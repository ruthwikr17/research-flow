from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["usage"])


@router.get("/usage")
def get_usage(request: Request) -> dict:
    services = request.app.state.services
    search_usage = services.search_service.get_credit_usage()
    rate_limit_usage = services.rate_limiter.get_status()

    quota_mon = services.quota_monitor
    llm_usage = {
        "groq": {
            "available": quota_mon.is_provider_available("groq"),
            "available_targets": quota_mon.get_available_targets("groq"),
        },
        "gemini": {
            "available": quota_mon.is_provider_available("gemini"),
            "available_targets": quota_mon.get_available_targets("gemini"),
            "total_projects": len(quota_mon.targets.get("gemini", [])),
        },
    }

    return {
        "search": search_usage,
        "llm": llm_usage,
        "rate_limit": rate_limit_usage,
    }
