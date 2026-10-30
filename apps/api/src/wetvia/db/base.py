"""Declarative base. No tables yet; the first migration is empty."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared metadata for later module tables."""
