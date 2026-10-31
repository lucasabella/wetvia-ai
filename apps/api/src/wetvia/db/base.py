"""Declarative base shared by feature-owned database schemas."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared metadata for later module tables."""
