"""Core data models for the extraction pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DataSource(str, Enum):
    YC = "ycombinator"
    PRODUCTHUNT = "producthunt"
    BETALIST = "betalist"
    F6S = "f6s"
    WELLFOUND = "wellfound"
    SAASHUB = "saashub"
    LAUNCHINGNEXT = "launchingnext"


class StartupRecord(BaseModel):
    """Canonical startup data schema."""

    name: str
    website: Optional[str] = None
    description: Optional[str] = None
    tagline: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None
    categories: list[str] = Field(default_factory=list)
    founded_year: Optional[int] = None
    funding_stage: Optional[str] = None
    team_size: Optional[str] = None
    tags: list[str] = Field(default_factory=list)

    source: DataSource
    source_url: Optional[str] = None
    profile_url: Optional[str] = None
    logo_url: Optional[str] = None

    # AI enrichment fields (populated by enricher)
    ai_industry_classification: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_tags: list[str] = Field(default_factory=list)

    # Metadata
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    quality_score: Optional[float] = None

    class Config:
        use_enum_values = True


class CrawlResult(BaseModel):
    """Wrapper for a batch of crawled records with metadata."""

    source: DataSource
    records: list[StartupRecord] = Field(default_factory=list)
    total_discovered: int = 0
    total_extracted: int = 0
    errors: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    class Config:
        use_enum_values = True


class FieldQuality(BaseModel):
    """Quality metrics for a single field."""

    field_name: str
    total: int
    populated: int
    missing: int
    completeness_pct: float


class QualityReport(BaseModel):
    """Data quality summary for the entire dataset."""

    total_records: int
    unique_records: int
    duplicates_removed: int
    field_quality: list[FieldQuality] = Field(default_factory=list)
    overall_completeness_pct: float = 0.0
    anomalies: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
