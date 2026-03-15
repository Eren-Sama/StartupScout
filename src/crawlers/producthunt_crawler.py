"""Product Hunt crawler — JS-rendered with Playwright."""

from __future__ import annotations

from typing import Optional

from bs4 import BeautifulSoup

from src.core.logging import get_logger
from src.core.models import DataSource, StartupRecord
from src.crawlers.base import BaseCrawler
from src.crawlers.browser import BrowserManager, scroll_to_bottom

logger = get_logger(__name__)


class ProductHuntCrawler(BaseCrawler):
    """Crawler for Product Hunt's product directory."""

    source = DataSource.PRODUCTHUNT
    base_url = "https://www.producthunt.com"

    def __init__(self, limit: Optional[int] = None):
        super().__init__(limit)
        self._browser = BrowserManager()

    async def discover_listings(self) -> list[str]:
        """Discover product URLs by scrolling through leaderboard pages."""
        urls: list[str] = []
        categories = ["tech", "saas", "ai", "developer-tools", "productivity"]

        await self._browser.start()

        for category in categories:
            try:
                async with self._browser.new_page() as page:
                    url = f"{self.base_url}/topics/{category}"
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await scroll_to_bottom(page, max_scrolls=10, wait_ms=2000)

                    html = await page.content()
                    soup = BeautifulSoup(html, "lxml")

                    for link in soup.find_all("a", href=True):
                        href = link["href"]
                        if href.startswith("/posts/") and href not in urls:
                            full_url = f"{self.base_url}{href}"
                            urls.append(full_url)

                    logger.info("producthunt.category", category=category, found=len(urls))

            except Exception as e:
                logger.warning("producthunt.discover_error", category=category, error=str(e))

            if self.limit and len(urls) >= self.limit:
                break

        return urls

    async def extract_profile(self, url: str) -> Optional[StartupRecord]:
        """Extract product details from a Product Hunt product page."""
        try:
            async with self._browser.new_page() as page:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                html = await page.content()

            soup = BeautifulSoup(html, "lxml")

            # Name from title or h1
            name = None
            h1 = soup.find("h1")
            if h1:
                name = h1.get_text(strip=True)
            if not name:
                title = soup.find("title")
                name = title.get_text(strip=True).split(" - ")[0] if title else "Unknown"

            # Tagline
            tagline = None
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                tagline = meta_desc["content"][:200]

            # Description — og:description or first long paragraph
            description = None
            og_desc = soup.find("meta", attrs={"property": "og:description"})
            if og_desc and og_desc.get("content"):
                description = og_desc["content"]

            # Website link
            website = None
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True).lower()
                if ("visit" in text or "website" in text) and href.startswith("http"):
                    website = href
                    break

            # Topics/tags
            tags = []
            for topic_link in soup.find_all("a", href=True):
                href = topic_link["href"]
                if "/topics/" in href:
                    tag = topic_link.get_text(strip=True)
                    if tag and tag not in tags:
                        tags.append(tag)

            return StartupRecord(
                name=name,
                website=website,
                description=description,
                tagline=tagline,
                categories=tags[:5],
                tags=tags,
                source=DataSource.PRODUCTHUNT,
                source_url=self.base_url,
                profile_url=url,
            )

        except Exception as e:
            logger.warning("producthunt.extract_error", url=url, error=str(e))
            return None

    async def cleanup(self) -> None:
        await self._browser.stop()
