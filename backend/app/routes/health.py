from fastapi import APIRouter, Request

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/services")
def services_health(request: Request) -> dict:
    services = request.app.state.services
    return {
        "status": "ok",
        "services": {
            "quota_monitor": {"status": "ok", "providers": list(services.quota_monitor.targets)},
            "search_service": {"status": "ok", "credit_usage": services.search_service.get_credit_usage()},
            "embed_service": {"status": "ok" if services.embed_service.is_ready else "unavailable", "model": services.embed_service.model_name},
        },
    }

