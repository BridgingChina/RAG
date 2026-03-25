"""Taxonomy management schemas."""
from __future__ import annotations
from uuid import UUID

from pydantic import BaseModel, field_validator


def _normalize_empty(v: str | None) -> str | None:
    """Convert empty/whitespace-only strings to None."""
    if v is not None:
        v = v.strip()
        if not v:
            return None
    return v


class TaxonomyNodeCreate(BaseModel):
    lvl1: str
    lvl2: str | None = None
    lvl3: str | None = None
    description: str | None = None

    @field_validator("lvl1", mode="before")
    @classmethod
    def strip_and_require_lvl1(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("lvl1 must not be empty")
        return v

    @field_validator("lvl2", "lvl3", "description", mode="before")
    @classmethod
    def normalize_optional(cls, v: str | None) -> str | None:
        return _normalize_empty(v)


class TaxonomyNodeUpdate(BaseModel):
    description: str | None = None


class TaxonomyNodeDetail(BaseModel):
    id: UUID
    lvl1: str
    lvl2: str | None
    lvl3: str | None
    description: str | None
    chunk_count: int


class TaxonomyTreeItem(BaseModel):
    node_id: UUID
    label: str
    chunk_count: int
    children: list[TaxonomyTreeItem]


class TaxonomyTree(BaseModel):
    items: list[TaxonomyTreeItem]


class TaxonomyBatchUpdate(BaseModel):
    chunk_ids: list[UUID]
    lvl1: str
    lvl2: str | None = None
    lvl3: str | None = None

    @field_validator("lvl1", mode="before")
    @classmethod
    def strip_and_require_lvl1(cls, v: str) -> str:
        if isinstance(v, str):
            v = v.strip()
        if not v:
            raise ValueError("lvl1 must not be empty")
        return v

    @field_validator("lvl2", "lvl3", mode="before")
    @classmethod
    def normalize_optional(cls, v: str | None) -> str | None:
        return _normalize_empty(v)


class TaxonomyBatchUpdateResult(BaseModel):
    updated_count: int
