"""Data normalization — clean raw scraped text into structured fields."""

from __future__ import annotations

import html
import re
from urllib.parse import urlparse, urlunparse

from src.core.logging import get_logger
from src.core.models import StartupRecord

logger = get_logger(__name__)

# Common location abbreviation mappings
LOCATION_ALIASES: dict[str, str] = {
    "SF": "San Francisco, CA, USA",
    "NYC": "New York, NY, USA",
    "NY": "New York, NY, USA",
    "LA": "Los Angeles, CA, USA",
    "LON": "London, UK",
    "BER": "Berlin, Germany",
}


def normalize_text(text: str | None) -> str | None:
    """Strip HTML, fix encoding, normalize whitespace."""
    if not text:
        return None

    # Decode HTML entities
    text = html.unescape(text)

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Remove zero-width characters
    text = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", text)

    return text if text else None


def normalize_url(url: str | None) -> str | None:
    """Clean and validate a URL."""
    if not url:
        return None

    url = url.strip()

    # Add scheme if missing
    if url and not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return None

        # Remove common tracking parameters
        clean_query = ""
        if parsed.query:
            tracking_params = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "ref", "fbclid", "gclid"}
            params = parsed.query.split("&")
            clean_params = [p for p in params if p.split("=")[0] not in tracking_params]
            clean_query = "&".join(clean_params)

        clean = urlunparse((
            parsed.scheme or "https",
            parsed.netloc.lower(),
            parsed.path.rstrip("/") or "/",
            parsed.params,
            clean_query,
            "",  # no fragment
        ))
        return clean

    except Exception:
        return None


def normalize_location(loc: str | None) -> str | None:
    """Standardize location strings."""
    if not loc:
        return None

    loc = normalize_text(loc)
    if not loc:
        return None

    # Check alias table
    upper = loc.upper().strip()
    if upper in LOCATION_ALIASES:
        return LOCATION_ALIASES[upper]

    # Clean common patterns
    loc = re.sub(r"\s*,\s*", ", ", loc)  # normalize comma spacing
    loc = re.sub(r"\s+", " ", loc)

    return loc


def normalize_record(record: StartupRecord) -> StartupRecord:
    """Apply all normalizations to a copy of the record (never mutates original)."""
    clean = record.model_copy()

    clean.name = normalize_text(clean.name) or clean.name
    clean.description = normalize_text(clean.description)
    clean.tagline = normalize_text(clean.tagline)
    clean.location = normalize_location(clean.location)
    clean.website = normalize_url(clean.website)
    clean.profile_url = normalize_url(clean.profile_url)
    clean.source_url = normalize_url(clean.source_url)
    clean.industry = normalize_text(clean.industry)
    clean.funding_stage = normalize_text(clean.funding_stage)
    clean.team_size = normalize_text(clean.team_size)

    # Clean tags
    clean.tags = [t.strip() for t in clean.tags if t and t.strip()]
    clean.categories = [c.strip() for c in clean.categories if c and c.strip()]

    # Trim overly long descriptions
    if clean.description and len(clean.description) > 2000:
        clean.description = clean.description[:2000] + "..."

    if clean.tagline and len(clean.tagline) > 200:
        clean.tagline = clean.tagline[:200] + "..."

    return clean


def normalize_batch(records: list[StartupRecord]) -> list[StartupRecord]:
    """Normalize an entire batch of records."""
    normalized = []
    for record in records:
        try:
            normalized.append(normalize_record(record))
        except Exception as e:
            logger.warning("normalize.error", name=record.name, error=str(e))
            normalized.append(record)

    logger.info("normalize.complete", count=len(normalized))
    return normalized
