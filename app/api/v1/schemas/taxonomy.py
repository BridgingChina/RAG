"""Taxonomy management schemas."""
from __future__ import annotations
from pydantic import BaseModel


class TaxonomyNodeCreate(BaseModel):
    lvl1: str
    lvl2: str | None = None
    lvl3: str | None = None
    description: str | None = None


class TaxonomyNodeUpdate(BaseModel):
    description: str | None = None


class TaxonomyNodeDetail(BaseModel):
    id: int
    lvl1: str
    lvl2: str | None
    lvl3: str | None
    description: str | None
    chunk_count: int


class TaxonomyTreeItem(BaseModel):
    label: str
    chunk_count: int
    children: list[TaxonomyTreeItem]


class TaxonomyTree(BaseModel):
    items: list[TaxonomyTreeItem]


class TaxonomyBatchUpdate(BaseModel):
    chunk_ids: list[int]
    lvl1: str
    lvl2: str | None = None
    lvl3: str | None = None


class TaxonomyBatchUpdateResult(BaseModel):
    updated_count: int
