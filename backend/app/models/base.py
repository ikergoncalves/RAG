"""SQLAlchemy declarative base.

ORM models for documents, chunks, and conversations are added in later phases
and must inherit from ``Base``.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
