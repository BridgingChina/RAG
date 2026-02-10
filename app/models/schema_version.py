"""Database schema version tracking."""

from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class SchemaVersion(Base, TimestampMixin):
    """Tracks applied database schema versions."""

    __tablename__ = "schema_version"

    version: Mapped[int] = mapped_column(primary_key=True)
    description: Mapped[str] = mapped_column()
