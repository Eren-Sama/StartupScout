"""Duplicate detection and record merging — two-phase: hash then fuzzy."""

from __future__ import annotations

from collections import defaultdict
from urllib.parse import urlparse

from Levenshtein import ratio as levenshtein_ratio

from src.core.logging import get_logger
from src.core.models import StartupRecord

logger = get_logger(__name__)

NAME_SIMILARITY_THRESHOLD = 0.85


def extract_domain(url: str | None) -> str | None:
    """Extract normalized domain from a URL."""
    if not url:
        return None
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain or None
    except Exception:
        return None


def _name_key(name: str) -> str:
    """Generate a blocking key from a name for fuzzy matching.

    Groups records by first 4 lowercase alphabetic characters.
    This reduces O(n²) comparisons to O(n·k) where k is the block size.
    """
    alpha = "".join(c for c in name.lower() if c.isalpha())
    return alpha[:4] if len(alpha) >= 4 else alpha


def records_are_duplicates(a: StartupRecord, b: StartupRecord) -> bool:
    """Determine if two records represent the same company."""
    if a.name and b.name:
        name_sim = levenshtein_ratio(a.name.lower().strip(), b.name.lower().strip())
        if name_sim >= NAME_SIMILARITY_THRESHOLD:
            return True
    return False


def merge_records(existing: StartupRecord, new: StartupRecord) -> StartupRecord:
    """Merge two duplicate records, preferring the most complete data."""
    merged = existing.model_copy()

    for field in ["website", "description", "tagline", "location", "industry",
                  "founded_year", "funding_stage", "team_size", "logo_url"]:
        existing_val = getattr(merged, field)
        new_val = getattr(new, field)

        if not existing_val and new_val:
            setattr(merged, field, new_val)
        elif existing_val and new_val:
            if field in ("description", "tagline") and isinstance(new_val, str):
                if len(str(new_val)) > len(str(existing_val)):
                    setattr(merged, field, new_val)

    for list_field in ["tags", "categories"]:
        existing_list = getattr(merged, list_field, [])
        new_list = getattr(new, list_field, [])
        combined = list(dict.fromkeys(existing_list + new_list))
        setattr(merged, list_field, combined)

    return merged


def deduplicate(records: list[StartupRecord]) -> tuple[list[StartupRecord], int]:
    """Two-phase deduplication: exact domain match, then fuzzy name match within blocks.

    Phase 1 (O(n)): Group by domain — exact match dedup.
    Phase 2 (O(n·k)): Group by name prefix — Levenshtein within blocks only.
    """
    # Phase 1: Exact domain dedup
    seen_domains: dict[str, int] = {}  # domain → index in unique list
    unique: list[StartupRecord] = []
    duplicates_count = 0

    for record in records:
        domain = extract_domain(record.website)
        if domain and domain in seen_domains:
            idx = seen_domains[domain]
            unique[idx] = merge_records(unique[idx], record)
            duplicates_count += 1
            continue

        unique.append(record)
        if domain:
            seen_domains[domain] = len(unique) - 1

    # Phase 2: Fuzzy name match within blocks (only for records without matching domains)
    blocks: dict[str, list[int]] = defaultdict(list)
    for i, record in enumerate(unique):
        if record.name:
            key = _name_key(record.name)
            blocks[key].append(i)

    merged_into: set[int] = set()

    for indices in blocks.values():
        for i in range(len(indices)):
            if indices[i] in merged_into:
                continue
            for j in range(i + 1, len(indices)):
                if indices[j] in merged_into:
                    continue
                if records_are_duplicates(unique[indices[i]], unique[indices[j]]):
                    unique[indices[i]] = merge_records(unique[indices[i]], unique[indices[j]])
                    merged_into.add(indices[j])
                    duplicates_count += 1

    final = [r for i, r in enumerate(unique) if i not in merged_into]

    logger.info(
        "dedup.complete",
        input=len(records),
        unique=len(final),
        duplicates=duplicates_count,
    )

    return final, duplicates_count
