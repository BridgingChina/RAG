"""Mobile knowledge schemas."""
from uuid import UUID
from pydantic import BaseModel


class KnowledgeTreeKP(BaseModel):
    """Knowledge point leaf node in the tree."""
    id: UUID
    name: str
    type: str = "knowledge_point"
    tags: list[str] = []
    summary: str | None = None


class KnowledgeTreeNode(BaseModel):
    """Taxonomy node in the tree (recursive)."""
    id: UUID
    name: str
    icon_url: str | None = None
    children: list["KnowledgeTreeNode | KnowledgeTreeKP"] = []


class KeyPointL0(BaseModel):
    id: UUID
    summary: str
    order: int


class KeyPointL1(BaseModel):
    id: UUID
    summary: str
    explanation: str | None
    illustrations: list[dict] = []
    related_terms: list[dict] = []
    citations: list[int] = []


class SourceRef(BaseModel):
    id: int
    title: str
    author: str | None = None
    type: str | None = None
    excerpt: str | None = None
    location: str | None = None
