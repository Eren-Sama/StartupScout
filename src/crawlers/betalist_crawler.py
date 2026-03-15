"""BetaList crawler — server-rendered HTML, httpx-based."""

from __future__ import annotations

from typing import Optional

from bs4 import BeautifulSoup

from src.core.logging import get_logger
from src.core.models import DataSource, StartupRecord
from src.crawlers.base import BaseCrawler
from src.crawlers.http_client import HttpClient

logger = get_logger(__name__)


class BetaListCrawler(BaseCrawler):
    """Crawler for BetaList startup directory."""

    source = DataSource.BETALIST
    base_url = "https://betalist.com/startups"

    def __init__(self, limit: Optional[int] = None):
        super().__init__(limit)
        self._http = HttpClient()

    async def discover_listings(self) -> list[str]:
        """Paginate through BetaList startup listing pages."""
        urls: list[str] = []
        page_num = 1
        max_pages = 50

        while page_num <= max_pages:
            try:
                url = f"{self.base_url}?page={page_num}"
                response = await self._http.get(url)
                soup = BeautifulSoup(response.text, "lxml")

                cards = soup.find_all("a", href=True)
                page_urls = []
                for card in cards:
                    href = card["href"]
                    if "/startups/" in href and href != "/startups":
                        full = f"https://betalist.com{href}" if href.startswith("/") else href
                        if full not in urls:
                            page_urls.append(full)

                if not page_urls:
                    break

                urls.extend(page_urls)
                logger.info("betalist.page", page=page_num, found=len(page_urls), total=len(urls))
                page_num += 1

                if self.limit and len(urls) >= self.limit:
                    break

            except Exception as e:
                logger.warning("betalist.discover_error", page=page_num, error=str(e))
                break

        return urls

    async def extract_profile(self, url: str) -> Optional[StartupRecord]:
        """Extract startup info from a BetaList profile page."""
        try:
            response = await self._http.get(url)
            soup = BeautifulSoup(response.text, "lxml")

            name = None
            h1 = soup.find("h1")
            if h1:
                name = h1.get_text(strip=True)

            if not name:
                title = soup.find("title")
                name = title.get_text(strip=True).split(" - ")[0] if title else "Unknown"

            tagline = None
            desc_el = soup.find("h2") or soup.find("p", class_=lambda x: x and "tagline" in str(x).lower())
            if desc_el:
                tagline = desc_el.get_text(strip=True)

            description = None
            meta = soup.find("meta", attrs={"name": "description"})
            if meta and meta.get("content"):
                description = meta["content"]

            website = None
            for link in soup.find_all("a", href=True, rel=lambda x: x and "nofollow" in x):
                href = link["href"]
                if href.startswith("http") and "betalist" not in href:
                    website = href
                    break

            tags = []
            for tag_el in soup.find_all("a", href=lambda h: h and "/markets/" in str(h)):
                tag_text = tag_el.get_text(strip=True)
                if tag_text:
                    tags.append(tag_text)

            return StartupRecord(
                name=name,
                website=website,
                description=description,
                tagline=tagline,
                tags=tags,
                categories=tags[:5],
                source=DataSource.BETALIST,
                source_url=self.base_url,
                profile_url=url,
            )

        except Exception as e:
            logger.warning("betalist.extract_error", url=url, error=str(e))
            return None

    async def cleanup(self) -> None:
        await self._http.close()
