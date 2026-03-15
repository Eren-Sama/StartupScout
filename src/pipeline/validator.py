"""Data validation and quality checks."""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urlparse

from src.core.logging import get_logger
from src.core.models import FieldQuality, QualityReport, StartupRecord

logger = get_logger(__name__)

REQUIRED_FIELDS = ["name"]
DESIRED_FIELDS = ["name", "website", "description", "tagline", "location", "industry", "categories"]
CURRENT_YEAR = datetime.now().year


def validate_url(url: str | None) -> bool:
    """Check if a URL is structurally valid."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        return bool(parsed.scheme in ("http", "https") and parsed.netloc and "." in parsed.netloc)
    except Exception:
        return False


def validate_year(year: int | None) -> bool:
    """Check if a founding year is plausible."""
    if year is None:
        return True  # missing is OK
    return 1900 <= year <= CURRENT_YEAR


def validate_record(record: StartupRecord) -> tuple[bool, list[str]]:
    """Validate a single record. Returns (is_valid, issues)."""
    issues: list[str] = []

    # Required field check
    if not record.name or not record.name.strip():
        issues.append("missing_name")

    # URL validation
    if record.website and not validate_url(record.website):
        issues.append(f"invalid_website_url: {record.website}")

    if record.profile_url and not validate_url(record.profile_url):
        issues.append(f"invalid_profile_url: {record.profile_url}")

    # Year validation
    if not validate_year(record.founded_year):
        issues.append(f"implausible_founded_year: {record.founded_year}")

    # Description quality
    if record.description and len(record.description) < 10:
        issues.append("description_too_short")

    # Name quality
    if record.name and len(record.name) > 200:
        issues.append("name_too_long")

    # Suspicious patterns
    if record.name and re.search(r"[<>{}\[\]]", record.name):
        issues.append("name_contains_html_artifacts")

    is_valid = "missing_name" not in issues
    return is_valid, issues


def validate_batch(records: list[StartupRecord]) -> tuple[list[StartupRecord], QualityReport]:
    """Validate batch of records and produce a quality report."""
    valid_records: list[StartupRecord] = []
    all_anomalies: list[str] = []

    for record in records:
        is_valid, issues = validate_record(record)
        if is_valid:
            if issues:
                record.quality_score = max(0, 1.0 - len(issues) * 0.15)
            else:
                record.quality_score = 1.0
            valid_records.append(record)
        else:
            all_anomalies.append(f"[REJECTED] {record.name or 'unnamed'}: {', '.join(issues)}")

    # Field-level completeness
    field_quality = []
    for field_name in DESIRED_FIELDS:
        total = len(valid_records)
        populated = sum(
            1 for r in valid_records
            if getattr(r, field_name, None) and (
                str(getattr(r, field_name)).strip() if not isinstance(getattr(r, field_name), list)
                else len(getattr(r, field_name)) > 0
            )
        )
        missing = total - populated
        pct = (populated / total * 100) if total > 0 else 0

        field_quality.append(FieldQuality(
            field_name=field_name,
            total=total,
            populated=populated,
            missing=missing,
            completeness_pct=round(pct, 1),
        ))

    overall = sum(fq.completeness_pct for fq in field_quality) / len(field_quality) if field_quality else 0

    report = QualityReport(
        total_records=len(records),
        unique_records=len(valid_records),
        duplicates_removed=0,  # set by deduplicator
        field_quality=field_quality,
        overall_completeness_pct=round(overall, 1),
        anomalies=all_anomalies,
    )

    logger.info(
        "validate.complete",
        total=len(records),
        valid=len(valid_records),
        rejected=len(records) - len(valid_records),
        completeness=f"{overall:.1f}%",
    )

    return valid_records, report
