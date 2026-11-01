"""HTTP routers."""

from wetvia.api.routes.chat import router as chat_router
from wetvia.api.routes.health import router as health_router
from wetvia.api.routes.rules import router as rules_router
from wetvia.api.routes.search import router as search_router

__all__ = ["chat_router", "health_router", "rules_router", "search_router"]
