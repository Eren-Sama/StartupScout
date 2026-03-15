"""F6S crawler — JS-rendered with Playwright."""

from __future__ import annotations

from typing import Optional

from bs4 import BeautifulSoup

from src.core.logging import get_logger
from src.core.models import DataSource, StartupRecord
from src.crawlers.base import BaseCrawler
from src.crawlers.browser import BrowserManager, scroll_to_bottom

logger = get_logger(__name__)


class F6SCrawler(BaseCrawler):
    """Crawler for F6S startup/founder directory."""

    source = DataSource.F6S
    base_url = "https://www.f6s.com"

    def __init__(self, limit: Optional[int] = None):
        super().__init__(limit)
        self._browser = BrowserManager()

    async def discover_listings(self) -> list[str]:
        """Discover startup URLs from F6S directory pages."""
        urls: list[str] = []
        pages_to_check = [
            f"{self.base_url}/startups",
            f"{self.base_url}/startups?page=2",
            f"{self.base_url}/startups?page=3",
            f"{self.base_url}/startups?page=4",
            f"{self.base_url}/startups?page=5",
        ]

        await self._browser.start()

        for page_url in pages_to_check:
            try:
                async with self._browser.new_page() as page:
                    await page.goto(page_url, wait_until="networkidle", timeout=30000)
                    await scroll_to_bottom(page, max_scrolls=8, wait_ms=2000)

                    html = await page.content()
                    soup = BeautifulSoup(html, "lxml")

                    for link in soup.find_all("a", href=True):
                        href = link["href"]
                        # F6S profile links look like /company-name
                        if (
                            href.startswith("/")
                            and not href.startswith("/startups")
                            and not href.startswith("/deals")
                            and not href.startswith("/jobs")
                            and not href.startswith("/events")
                            and "/" not in href[1:]
                            and len(href) > 2
                        ):
                            full_url = f"{self.base_url}{href}"
                            if full_url not in urls:
                                urls.append(full_url)

                    logger.info("f6s.page", url=page_url, found=len(urls))

            except Exception as e:
                logger.warning("f6s.discover_error", url=page_url, error=str(e))

            if self.limit and len(urls) >= self.limit:
                break

        return urls

    async def extract_profile(self, url: str) -> Optional[StartupRecord]:
        """Extract startup info from F6S profile page."""
        try:
            async with self._browser.new_page() as page:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                html = await page.content()

            soup = BeautifulSoup(html, "lxml")

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
            subtitle = soup.find("h2") or soup.find(class_=lambda x: x and "subtitle" in str(x).lower())
            if subtitle:
                tagline = subtitle.get_text(strip=True)[:200]

            location = None
            for el in soup.find_all(["span", "div"], string=True):
                text = el.get_text(strip=True)
                if any(indicator in text.lower() for indicator in ["based in", "located in", ","]):
                    if len(text) < 100 and any(c.isupper() for c in text):
                        location = text
                        break

            website = None
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text(strip=True).lower()
                if href.startswith("http") and "f6s.com" not in href:
                    if "website" in text or "visit" in text or "www" in href:
                        website = href
                        break

            tags = []
            for tag_el in soup.find_all("a", href=lambda h: h and "/tag/" in str(h)):
                tag_text = tag_el.get_text(strip=True)
                if tag_text and tag_text not in tags:
                    tags.append(tag_text)

            return StartupRecord(
                name=name,
                website=website,
                description=description,
                tagline=tagline,
                location=location,
                tags=tags,
                categories=tags[:5],
                source=DataSource.F6S,
                source_url=self.base_url,
                profile_url=url,
            )

        except Exception as e:
            logger.warning("f6s.extract_error", url=url, error=str(e))
            return None

    async def cleanup(self) -> None:
        await self._browser.stop()
