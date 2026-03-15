"""Wellfound (formerly AngelList) crawler — Playwright-based."""

from __future__ import annotations

from typing import Optional

from bs4 import BeautifulSoup

from src.core.logging import get_logger
from src.core.models import DataSource, StartupRecord
from src.crawlers.base import BaseCrawler
from src.crawlers.browser import BrowserManager, scroll_to_bottom

logger = get_logger(__name__)


class WellfoundCrawler(BaseCrawler):
    """Crawler for Wellfound (formerly AngelList Talent) startup directory."""

    source = DataSource.WELLFOUND
    base_url = "https://wellfound.com"

    def __init__(self, limit: Optional[int] = None):
        super().__init__(limit)
        self._browser = BrowserManager()

    async def discover_listings(self) -> list[str]:
        """Discover startup profile URLs from Wellfound directory."""
        urls: list[str] = []

        await self._browser.start()

        page_num = 1
        max_pages = 10

        while page_num <= max_pages:
            try:
                async with self._browser.new_page() as page:
                    url = f"{self.base_url}/startups?page={page_num}"
                    try:
                        await page.goto(url, wait_until="load", timeout=15000)
                        await page.wait_for_timeout(2000)
                    except Exception as goto_err:
                        logger.debug("wf_goto_timeout", warn=str(goto_err))
                    await scroll_to_bottom(page, max_scrolls=5, wait_ms=2000)

                    html = await page.content()
                    soup = BeautifulSoup(html, "lxml")

                    found_on_page = 0
                    for link in soup.find_all("a", href=True):
                        href = link["href"]
                        if "/company/" in href:
                            full_url = f"{self.base_url}{href}" if href.startswith("/") else href
                            if full_url not in urls:
                                urls.append(full_url)
                                found_on_page += 1

                    logger.info("wellfound.page", page=page_num, found=found_on_page, total=len(urls))

                    if found_on_page == 0:
                        break

                page_num += 1

            except Exception as e:
                logger.warning("wellfound.discover_error", page=page_num, error=str(e))
                break

            if self.limit and len(urls) >= self.limit:
                break

        return urls

    async def extract_profile(self, url: str) -> Optional[StartupRecord]:
        """Extract startup details from Wellfound company page."""
        try:
            async with self._browser.new_page() as page:
                try:
                    await page.goto(url, wait_until="load", timeout=15000)
                    await page.wait_for_timeout(2000)
                except Exception as ex:
                    logger.debug("wf_goto_profile_timeout", warn=str(ex))
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
            for el in soup.find_all(["p", "span"]):
                text = el.get_text(strip=True)
                if 20 < len(text) < 200 and not text.startswith("http"):
                    tagline = text
                    break

            location = None
            for el in soup.find_all(["span", "div"]):
                text = el.get_text(strip=True)
                if any(city in text for city in ["San Francisco", "New York", "London", "Berlin", "Remote"]):
                    location = text
                    break

            website = None
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                if href.startswith("http") and "wellfound" not in href and "angel" not in href:
                    website = href
                    break

            team_size = None
            for el in soup.find_all(string=True):
                text = str(el).strip()
                if "employees" in text.lower() or "team" in text.lower():
                    team_size = text[:50]
                    break

            markets = []
            for tag_el in soup.find_all("a", href=lambda h: h and "/markets/" in str(h)):
                tag_text = tag_el.get_text(strip=True)
                if tag_text and tag_text not in markets:
                    markets.append(tag_text)

            return StartupRecord(
                name=name,
                website=website,
                description=description,
                tagline=tagline,
                location=location,
                team_size=team_size,
                tags=markets,
                categories=markets[:5],
                source=DataSource.WELLFOUND,
                source_url=self.base_url,
                profile_url=url,
            )

        except Exception as e:
            logger.warning("wellfound.extract_error", url=url, error=str(e))
            return None

    async def cleanup(self) -> None:
        await self._browser.stop()
