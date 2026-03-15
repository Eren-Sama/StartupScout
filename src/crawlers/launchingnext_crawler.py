"""Launching Next crawler — simple HTML pages, httpx-based."""

from __future__ import annotations

from typing import Optional

from bs4 import BeautifulSoup

from src.core.logging import get_logger
from src.core.models import DataSource, StartupRecord
from src.crawlers.base import BaseCrawler
from src.crawlers.http_client import HttpClient

logger = get_logger(__name__)


class LaunchingNextCrawler(BaseCrawler):
    """Crawler for Launching Next startup submissions directory."""

    source = DataSource.LAUNCHINGNEXT
    base_url = "https://www.launchingnext.com"

    def __init__(self, limit: Optional[int] = None):
        super().__init__(limit)
        self._http = HttpClient()

    async def discover_listings(self) -> list[str]:
        """Paginate through Launching Next startup pages."""
        urls: list[str] = []
        page_num = 1
        max_pages = 20

        while page_num <= max_pages:
            try:
                url = f"{self.base_url}/startups?page={page_num}"
                response = await self._http.get(url)
                soup = BeautifulSoup(response.text, "lxml")

                found_on_page = 0
                for link in soup.find_all("a", href=True):
                    href = link["href"]
                    if "/startup/" in href or "/s/" in href:
                        full_url = f"{self.base_url}{href}" if href.startswith("/") else href
                        if full_url not in urls:
                            urls.append(full_url)
                            found_on_page += 1

                if found_on_page == 0:
                    break

                logger.info("launchingnext.page", page=page_num, found=found_on_page, total=len(urls))
                page_num += 1

            except Exception as e:
                logger.warning("launchingnext.discover_error", page=page_num, error=str(e))
                break

            if self.limit and len(urls) >= self.limit:
                break

        return urls

    async def extract_profile(self, url: str) -> Optional[StartupRecord]:
        """Extract startup info from Launching Next detail page."""
        try:
            response = await self._http.get(url)
            soup = BeautifulSoup(response.text, "lxml")

            name = None
            h1 = soup.find("h1")
            if h1:
                name = h1.get_text(strip=True)
            if not name:
                title = soup.find("title")
                name = title.get_text(strip=True).split(" | ")[0] if title else "Unknown"

            tagline = None
            h2 = soup.find("h2")
            if h2:
                tagline = h2.get_text(strip=True)[:200]

            description = None
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                description = meta_desc["content"]

            # Look for fuller description in page body
            for p in soup.find_all("p"):
                text = p.get_text(strip=True)
                if len(text) > 100:
                    description = text
                    break

            website = None
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True).lower()
                if href.startswith("http") and "launchingnext" not in href:
                    if "visit" in text or "website" in text or "url" in text:
                        website = href
                        break

            if not website:
                for link in soup.find_all("a", href=True, rel="nofollow"):
                    href = link["href"]
                    if href.startswith("http") and "launchingnext" not in href:
                        website = href
                        break

            tags = []
            for tag_el in soup.find_all("a", href=lambda h: h and ("/category/" in str(h) or "/tag/" in str(h))):
                tag_text = tag_el.get_text(strip=True)
                if tag_text and tag_text not in tags:
                    tags.append(tag_text)

            return StartupRecord(
                name=name,
                website=website,
                description=description,
                tagline=tagline,
                tags=tags,
                categories=tags[:5],
                source=DataSource.LAUNCHINGNEXT,
                source_url=self.base_url,
                profile_url=url,
            )

        except Exception as e:
            logger.warning("launchingnext.extract_error", url=url, error=str(e))
            return None

    async def cleanup(self) -> None:
        await self._http.close()
