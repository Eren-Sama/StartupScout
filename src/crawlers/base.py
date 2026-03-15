"""Abstract base crawler with shared infrastructure."""

from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from typing import Optional

from src.core.config import settings
from src.core.logging import get_logger
from src.core.models import CrawlResult, DataSource, StartupRecord

logger = get_logger(__name__)


class BaseCrawler(ABC):
    """Base class for all directory crawlers."""

    source: DataSource
    base_url: str

    def __init__(self, limit: Optional[int] = None):
        self.limit = limit
        self.records: list[StartupRecord] = []
        self.errors: list[str] = []
        self._request_count = 0

    @abstractmethod
    async def discover_listings(self) -> list[str]:
        """Discover company listing/profile URLs from directory pages."""

    @abstractmethod
    async def extract_profile(self, url: str) -> Optional[StartupRecord]:
        """Extract structured data from a single company profile page."""

    async def run(self) -> CrawlResult:
        """Execute the full crawl pipeline for this source."""
        from datetime import datetime

        started = datetime.utcnow()
        logger.info("crawl.start", source=self.source.value, limit=self.limit)

        profile_urls = await self.discover_listings()
        total_discovered = len(profile_urls)
        logger.info("crawl.discovered", source=self.source.value, count=total_discovered)

        if self.limit:
            profile_urls = profile_urls[: self.limit]

        concurrency = settings.crawler.concurrency
        semaphore = asyncio.Semaphore(concurrency)

        async def _extract_with_limit(url: str) -> Optional[StartupRecord]:
            async with semaphore:
                await self._respectful_delay()
                try:
                    return await self.extract_profile(url)
                except Exception as e:
                    self.errors.append(f"[{url}] {e}")
                    logger.warning("crawl.extract_error", url=url, error=str(e))
                    return None

        tasks = [_extract_with_limit(url) for url in profile_urls]
        results = await asyncio.gather(*tasks, return_exceptions=False)

        self.records = [r for r in results if r is not None]
        finished = datetime.utcnow()

        result = CrawlResult(
            source=self.source,
            records=self.records,
            total_discovered=total_discovered,
            total_extracted=len(self.records),
            errors=self.errors,
            started_at=started,
            finished_at=finished,
            duration_seconds=(finished - started).total_seconds(),
        )

        logger.info(
            "crawl.complete",
            source=self.source.value,
            extracted=result.total_extracted,
            errors=len(result.errors),
            duration=f"{result.duration_seconds:.1f}s",
        )
        return result

    async def _respectful_delay(self) -> None:
        """Random delay between requests to be polite."""
        delay = random.uniform(settings.crawler.delay_min, settings.crawler.delay_max)
        await asyncio.sleep(delay)
