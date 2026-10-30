"""HTTP boundary. The composition root is ``wetvia.bootstrap``, not this package."""

from wetvia.api.app import create_app

__all__ = ["create_app"]
