from pydantic import BaseModel


class AskContext(BaseModel):
    bridge_id: int | None = None
    lvl1: str | None = None
    lvl2: str | None = None
    lvl3: str | None = None


class AskRequest(BaseModel):
    question: str
    context: AskContext | None = None


class CitationResponse(BaseModel):
    chunk_id: int
    source_title: str
    page_range: str | None


class AskResponse(BaseModel):
    summary: str
    details: str
    citations: list[CitationResponse]
    sources: list[str]
