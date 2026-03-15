"""Y Combinator directory crawler — direct Algolia API integration."""

from __future__ import annotations

from typing import Optional

import httpx

from src.core.config import settings
from src.core.logging import get_logger
from src.core.models import DataSource, StartupRecord
from src.crawlers.base import BaseCrawler

logger = get_logger(__name__)


class YCCrawler(BaseCrawler):
    """Crawler for Y Combinator's company directory via Algolia API.

    Uses the same public Algolia search index that the YC website uses.
    Credentials are loaded from config (AlgoliaSettings), not hardcoded.
    """

    source = DataSource.YC
    base_url = "https://www.ycombinator.com/companies"

    def __init__(self, limit: Optional[int] = None):
        super().__init__(limit)
        self._hits: list[dict] = []

    async def discover_listings(self) -> list[str]:
        """Fetch all company records via Algolia API pagination."""
        page = 0
        hits_per_page = 1000
        total_hits: list[dict] = []

        algolia_url = settings.algolia.url
        app_id = settings.algolia.app_id
        api_key = settings.algolia.api_key.get_secret_value()

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                try:
                    body = {
                        "requests": [
                            {
                                "indexName": "YCCompany_production",
                                "params": f"hitsPerPage={hits_per_page}&page={page}&query=&tagFilters=",
                            }
                        ]
                    }

                    resp = await client.post(
                        algolia_url,
                        json=body,
                        headers={
                            "x-algolia-application-id": app_id,
                            "x-algolia-api-key": api_key,
                            "Content-Type": "application/json",
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    results = data.get("results", [])
                    if not results:
                        break

                    hits = results[0].get("hits", [])
                    if not hits:
                        break

                    total_hits.extend(hits)
                    nb_pages = results[0].get("nbPages", 0)
                    page += 1

                    logger.info("yc.api_page", page=page, hits=len(hits), total=len(total_hits))

                    if page >= nb_pages:
                        break

                    if self.limit and len(total_hits) >= self.limit:
                        total_hits = total_hits[: self.limit]
                        break

                except Exception as e:
                    logger.warning("yc.api_error", page=page, error=str(e))
                    break

        self._hits = total_hits
        logger.info("yc.discovered", total=len(total_hits))

        return [hit.get("slug", f"hit_{i}") for i, hit in enumerate(total_hits)]

    async def extract_profile(self, url: str) -> Optional[StartupRecord]:
        """Convert an Algolia API hit into a StartupRecord."""
        hit = None
        for h in self._hits:
            if h.get("slug") == url:
                hit = h
                break

        if not hit:
            return None

        try:
            name = hit.get("name", "")
            slug = hit.get("slug", "")

            locations = hit.get("all_locations", "")
            if isinstance(locations, list):
                locations = ", ".join(locations)

            industry = hit.get("industry", "")
            subindustry = hit.get("subindustry", "")
            industries = hit.get("industries", [])
            tags = industries if isinstance(industries, list) else []
            primary_industry = industry or (tags[0] if tags else None)

            record = StartupRecord(
                name=name,
                website=hit.get("website", None),
                description=hit.get("long_description", None),
                tagline=hit.get("one_liner", None),
                location=locations or None,
                industry=primary_industry,
                categories=tags[:5] if tags else [],
                founded_year=None,
                funding_stage=hit.get("stage", None),
                team_size=str(hit.get("team_size", "")) if hit.get("team_size") else None,
                tags=tags + ([subindustry] if subindustry and subindustry not in tags else []),
                source=DataSource.YC,
                source_url=self.base_url,
                profile_url=f"https://www.ycombinator.com/companies/{slug}",
            )

            # Free memory: remove processed hit
            self._hits.remove(hit)

            return record

        except Exception as e:
            logger.warning("yc.extract_error", slug=url, error=str(e))
            return None

    async def cleanup(self) -> None:
        self._hits.clear()
