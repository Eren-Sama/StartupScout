"""SaaSHub crawler — server-rendered HTML, httpx-based."""

from __future__ import annotations

from typing import Optional

from bs4 import BeautifulSoup

from src.core.logging import get_logger
from src.core.models import DataSource, StartupRecord
from src.crawlers.base import BaseCrawler
from src.crawlers.http_client import HttpClient

logger = get_logger(__name__)


class SaaSHubCrawler(BaseCrawler):
    """Crawler for SaaSHub software/startup directory."""

    source = DataSource.SAASHUB
    base_url = "https://www.saashub.com"

    def __init__(self, limit: Optional[int] = None):
        super().__init__(limit)
        self._http = HttpClient()

    async def discover_listings(self) -> list[str]:
        """Paginate through SaaSHub category pages."""
        urls: list[str] = []
        categories = [
            "best-startup-tools",
            "best-saas-products",
            "best-ai-tools",
            "best-developer-tools",
            "best-marketing-tools",
            "best-productivity-tools",
        ]

        for category in categories:
            page_num = 1
            max_pages = 5

            while page_num <= max_pages:
                try:
                    url = f"{self.base_url}/{category}?page={page_num}"
                    response = await self._http.get(url)
                    soup = BeautifulSoup(response.text, "lxml")

                    found_on_page = 0
                    for link in soup.find_all("a", href=True):
                        href = link["href"]
                        if href.startswith("/") and not any(
                            skip in href for skip in ["/best-", "/alternatives/", "/vs/", "/categories/", "/login", "/signup"]
                        ):
                            # SaaSHub product pages are like /product-name
                            if "/" not in href[1:] and len(href) > 2:
                                full_url = f"{self.base_url}{href}"
                                if full_url not in urls:
                                    urls.append(full_url)
                                    found_on_page += 1

                    if found_on_page == 0:
                        break

                    logger.info("saashub.page", category=category, page=page_num, found=found_on_page)
                    page_num += 1

                except Exception as e:
                    logger.warning("saashub.discover_error", category=category, page=page_num, error=str(e))
                    break

            if self.limit and len(urls) >= self.limit:
                break

        return urls

    async def extract_profile(self, url: str) -> Optional[StartupRecord]:
        """Extract software/startup details from SaaSHub product page."""
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

            description = None
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc and meta_desc.get("content"):
                description = meta_desc["content"]

            tagline = None
            subtitle = soup.find("h2")
            if subtitle:
                tagline = subtitle.get_text(strip=True)[:200]

            website = None
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True).lower()
                if href.startswith("http") and "saashub" not in href:
                    if "visit" in text or "website" in text or "official" in text:
                        website = href
                        break

            if not website:
                for link in soup.find_all("a", href=True, rel="nofollow"):
                    href = link["href"]
                    if href.startswith("http") and "saashub" not in href:
                        website = href
                        break

            categories = []
            for cat_link in soup.find_all("a", href=lambda h: h and "/categories/" in str(h)):
                cat_text = cat_link.get_text(strip=True)
                if cat_text and cat_text not in categories:
                    categories.append(cat_text)

            tags = []
            for tag_link in soup.find_all("a", href=lambda h: h and "/tag/" in str(h)):
                tag_text = tag_link.get_text(strip=True)
                if tag_text and tag_text not in tags:
                    tags.append(tag_text)

            return StartupRecord(
                name=name,
                website=website,
                description=description,
                tagline=tagline,
                categories=categories[:5],
                tags=tags,
                source=DataSource.SAASHUB,
                source_url=self.base_url,
                profile_url=url,
            )

        except Exception as e:
            logger.warning("saashub.extract_error", url=url, error=str(e))
            return None

    async def cleanup(self) -> None:
        await self._http.close()
