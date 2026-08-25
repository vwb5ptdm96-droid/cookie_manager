from fastapi import APIRouter

from app.core.response import success_response

router = APIRouter(tags=["health"])


@router.get("/health")
def get_health() -> dict[str, object]:
    return success_response(
        {
            "status": "ok",
            "service": "session-maintenance-system",
        }
    )

