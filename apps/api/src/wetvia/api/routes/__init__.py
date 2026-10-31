"""HTTP routers."""

from wetvia.api.routes.health import router as health_router
from wetvia.api.routes.search import router as search_router

__all__ = ["health_router", "search_router"]
