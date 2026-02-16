"""Dashboard stats schemas."""
from datetime import datetime
from pydantic import BaseModel


class BindingDistribution(BaseModel):
    primary: int
    ambiguous: int
    none: int


class Lvl1Distribution(BaseModel):
    label: str
    count: int


class RecentIngest(BaseModel):
    source_id: int
    title: str | None
    chunk_count: int
    created_at: datetime


class DashboardStats(BaseModel):
    chunk_count: int
    bridge_count: int
    source_count: int
    ambiguous_ratio: float
    binding_distribution: BindingDistribution
    lvl1_distribution: list[Lvl1Distribution]
    recent_ingests: list[RecentIngest]
