"""Resilient async HTTP client with retries, rate limiting, response guards, and header rotation."""

from __future__ import annotations

import asyncio
import random
import time

import httpx
from fake_useragent import UserAgent
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 MB

BLOCK_MARKERS = [
    "captcha", "cf-challenge", "cloudflare", "access denied",
    "please verify you are a human", "blocked", "rate limit exceeded",
]

# Fallback UA list in case fake-useragent's remote fetch fails
FALLBACK_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
]


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, rate: float = 1.0, burst: int = 5):
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            self._last_refill = now

            if self._tokens < 1:
                wait_time = (1 - self._tokens) / self._rate
                await asyncio.sleep(wait_time)
                self._tokens = 0
            else:
                self._tokens -= 1


class BlockDetectedError(Exception):
    """Raised when a CAPTCHA/block page is detected."""


class ResponseTooLargeError(Exception):
    """Raised when response exceeds MAX_RESPONSE_BYTES."""


class HttpClient:
    """Production-grade async HTTP client with safety guards."""

    def __init__(self):
        try:
            self._ua = UserAgent(browsers=["chrome", "firefox", "edge"])
        except Exception:
            self._ua = None
        self._rate_limiter = RateLimiter(rate=2.0, burst=5)
        self._client: httpx.AsyncClient | None = None

    def _get_random_ua(self) -> str:
        try:
            if self._ua:
                return self._ua.random
        except Exception:
            pass
        return random.choice(FALLBACK_USER_AGENTS)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.crawler.timeout, connect=10.0),
                follow_redirects=True,
                http2=False,  # Disabled to circumvent Cloudflare HTTP/2 fingerprinting returning 404
                limits=httpx.Limits(
                    max_connections=settings.crawler.concurrency * 2,
                    max_keepalive_connections=settings.crawler.concurrency,
                ),
            )
        return self._client

    def _random_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._get_random_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
            "Accept-Language": "en-US,en;q=0.9,en-GB;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "sec-ch-ua": "\"Google Chrome\";v=\"124\", \"Chromium\";v=\"124\", \"Not-A.Brand\";v=\"99\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        }

    def _check_response_size(self, response: httpx.Response) -> None:
        content_length = response.headers.get("content-length")
        if content_length and int(content_length) > MAX_RESPONSE_BYTES:
            raise ResponseTooLargeError(
                f"Response too large: {int(content_length)} bytes (max {MAX_RESPONSE_BYTES})"
            )

    def _check_for_blocks(self, response: httpx.Response) -> None:
        if response.status_code == 429:
            raise BlockDetectedError("Rate limited (HTTP 429)")

        # Only check HTML responses
        content_type = response.headers.get("content-type", "")
        if "text/html" not in content_type:
            return

        # Check first 2KB for block markers
        snippet = response.text[:2048].lower()
        for marker in BLOCK_MARKERS:
            if marker in snippet:
                raise BlockDetectedError(f"Block/CAPTCHA detected: '{marker}' found in response")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout)),
    )
    async def get(self, url: str, **kwargs) -> httpx.Response:
        """GET request with retry, rate limiting, size guard, and block detection."""
        await self._rate_limiter.acquire()
        client = await self._get_client()
        headers = {**self._random_headers(), **kwargs.pop("headers", {})}

        response = await client.get(url, headers=headers, **kwargs)
        self._check_response_size(response)
        response.raise_for_status()
        self._check_for_blocks(response)

        logger.debug("http.get", url=url, status=response.status_code)
        return response

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout)),
    )
    async def get_json(self, url: str, **kwargs) -> dict:
        """GET request expecting JSON response."""
        await self._rate_limiter.acquire()
        client = await self._get_client()
        headers = {
            **self._random_headers(),
            "Accept": "application/json",
            **kwargs.pop("headers", {}),
        }

        response = await client.get(url, headers=headers, **kwargs)
        self._check_response_size(response)
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
