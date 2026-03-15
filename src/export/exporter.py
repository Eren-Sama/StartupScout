"""Data export to CSV and JSON formats."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.core.config import settings
from src.core.logging import get_logger
from src.core.models import QualityReport, StartupRecord

logger = get_logger(__name__)


class CSVExporter:
    """Export startup records to CSV."""

    COLUMNS = [
        "name", "website", "tagline", "description", "location",
        "industry", "categories", "founded_year", "funding_stage",
        "team_size", "tags", "source", "profile_url",
        "ai_industry_classification", "ai_summary", "ai_tags",
        "quality_score", "scraped_at",
    ]

    def export(self, records: list[StartupRecord], output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / "startups.csv"

        rows = []
        for r in records:
            row = {
                "name": r.name,
                "website": r.website,
                "tagline": r.tagline,
                "description": r.description,
                "location": r.location,
                "industry": r.industry,
                "categories": "; ".join(r.categories) if r.categories else "",
                "founded_year": r.founded_year,
                "funding_stage": r.funding_stage,
                "team_size": r.team_size,
                "tags": "; ".join(r.tags) if r.tags else "",
                "source": r.source,
                "profile_url": r.profile_url,
                "ai_industry_classification": r.ai_industry_classification,
                "ai_summary": r.ai_summary,
                "ai_tags": "; ".join(r.ai_tags) if r.ai_tags else "",
                "quality_score": r.quality_score,
                "scraped_at": r.scraped_at.isoformat() if r.scraped_at else "",
            }
            rows.append(row)

        df = pd.DataFrame(rows, columns=self.COLUMNS)
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        logger.info("export.csv", path=str(filepath), records=len(records))
        return filepath


class JSONExporter:
    """Export startup records to JSON with metadata."""

    def export(self, records: list[StartupRecord], output_dir: Path, quality_report: QualityReport | None = None) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        filepath = output_dir / "startups.json"

        output = {
            "metadata": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_records": len(records),
                "sources": list(set(r.source for r in records)),
                "quality": {
                    "overall_completeness_pct": quality_report.overall_completeness_pct if quality_report else None,
                    "duplicates_removed": quality_report.duplicates_removed if quality_report else 0,
                },
            },
            "records": [r.model_dump(mode="json") for r in records],
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False, default=str)

        logger.info("export.json", path=str(filepath), records=len(records))
        return filepath


def export_quality_report(report: QualityReport, output_dir: Path) -> Path:
    """Export the quality report as a standalone JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filepath = output_dir / "quality_report.json"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(mode="json"), f, indent=2, default=str)

    logger.info("export.quality_report", path=str(filepath))
    return filepath


def run_export(records: list[StartupRecord], quality_report: QualityReport | None = None) -> list[Path]:
    """Run all configured exporters."""
    output_dir = settings.export.output_dir
    formats = [f.strip().lower() for f in settings.export.format.split(",")]
    exported: list[Path] = []

    if "csv" in formats:
        path = CSVExporter().export(records, output_dir)
        exported.append(path)

    if "json" in formats:
        path = JSONExporter().export(records, output_dir, quality_report)
        exported.append(path)

    if quality_report:
        path = export_quality_report(quality_report, output_dir)
        exported.append(path)

    return exported
