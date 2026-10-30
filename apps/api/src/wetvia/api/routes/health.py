"""``GET /api/health``. Dependencies are injected; this module does not read the environment."""

from typing import Annotated

from fastapi import APIRouter, Depends

from wetvia.api.deps import HealthContext, get_health_context
from wetvia.api.schemas.health import HealthResponse

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def read_health(
    context: Annotated[HealthContext, Depends(get_health_context)],
) -> HealthResponse:
    db_status = await context.check_db()
    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        db=db_status,
        llm_provider=context.llm_provider,
        version=context.version,
    )
