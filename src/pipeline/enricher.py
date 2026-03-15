"""AI-powered data enrichment via Groq LLM with concurrency and prompt sanitization."""

from __future__ import annotations

import asyncio
import json
import re

from src.core.config import settings
from src.core.logging import get_logger
from src.core.models import StartupRecord

logger = get_logger(__name__)

CLASSIFICATION_PROMPT = """You are a startup analyst. Given the following startup information, provide:
1. industry_classification: The primary industry sector (e.g., "AI/ML", "FinTech", "HealthTech", "EdTech", "SaaS", "E-Commerce", "DevTools", "Cybersecurity", "CleanTech", "MarTech", "HRTech", "PropTech", "InsurTech", "LegalTech", "FoodTech", "Gaming", "Social", "Marketplace", "Enterprise", "Consumer", "Other")
2. summary: A concise 1-2 sentence summary of what the company does (max 150 chars)
3. tags: Up to 5 relevant tags as a JSON array

Startup info:
- Name: {name}
- Description: {description}
- Tagline: {tagline}
- Categories: {categories}
- Industry: {industry}

Respond ONLY with valid JSON in this exact format:
{{"industry_classification": "...", "summary": "...", "tags": ["tag1", "tag2"]}}"""


def sanitize_for_prompt(text: str | None, max_len: int = 1500) -> str:
    """Sanitize input text to prevent basic prompt injections and limit length."""
    if not text:
        return ""
    # Strip dangerous payload markers
    clean = re.sub(r"(?i)(ignore previous instructions|system prompt|you are now)", "", text)
    # Strip markdown/json code blocks to avoid breaking formatting
    clean = re.sub(r"```[a-z]*", "", clean)
    clean = clean.replace("{", "(").replace("}", ")")
    return clean[:max_len].strip()


class AIEnricher:
    """Enriches startup records using Groq LLM concurrently."""

    def __init__(self):
        self._client = None
        self._enabled = settings.llm.is_configured
        # Limit concurrent requests to respect rate limits
        self._semaphore = asyncio.Semaphore(settings.llm.batch_size)

    def _get_client(self):
        if self._client is None:
            from groq import Groq
            # get_secret_value since api_key is now SecretStr
            self._client = Groq(api_key=settings.llm.api_key.get_secret_value())
        return self._client

    async def enrich_record(self, record: StartupRecord) -> StartupRecord:
        """Enrich a single record with AI classifications."""
        if not self._enabled:
            return record

        if not record.description and not record.tagline:
            return record

        try:
            prompt = CLASSIFICATION_PROMPT.format(
                name=sanitize_for_prompt(record.name, 100),
                description=sanitize_for_prompt(record.description, 1000),
                tagline=sanitize_for_prompt(record.tagline, 200),
                categories=sanitize_for_prompt(", ".join(record.categories) if record.categories else "", 200),
                industry=sanitize_for_prompt(record.industry, 100),
            )

            client = self._get_client()
            loop = asyncio.get_running_loop()

            async with self._semaphore:
                response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
                    model=settings.llm.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=settings.llm.temperature,
                    max_tokens=settings.llm.max_tokens,
                    response_format={"type": "json_object"},
                ))

                # Respect RPM dynamically by adding a short delay before releasing semaphore
                delay = 60.0 / settings.llm.rate_limit_rpm
                await asyncio.sleep(delay)

            content = response.choices[0].message.content
            data = json.loads(content)

            record.ai_industry_classification = data.get("industry_classification")
            record.ai_summary = data.get("summary")
            record.ai_tags = data.get("tags", [])

            logger.debug("enrich.success", name=record.name, industry=record.ai_industry_classification)

        except json.JSONDecodeError as e:
            logger.warning("enrich.json_error", name=record.name, error=str(e))
        except Exception as e:
            logger.warning("enrich.error", name=record.name, error=str(e))

        return record

    async def enrich_batch(self, records: list[StartupRecord]) -> list[StartupRecord]:
        """Enrich a batch of records concurrently."""
        if not self._enabled:
            logger.info("enrich.skipped", reason="GROQ_API_KEY not configured")
            return records

        logger.info("enrich.start", count=len(records))

        tasks = [self.enrich_record(r) for r in records]
        
        # We can gather all tasks because semaphore bounds concurrency internally
        enriched = await asyncio.gather(*tasks, return_exceptions=False)

        logger.info("enrich.complete", enriched=len(enriched))
        return enriched
