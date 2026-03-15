"""Pipeline orchestrator — chains crawl → normalize → validate → dedup → enrich → export."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from src.core.logging import get_logger
from src.core.models import CrawlResult, QualityReport, StartupRecord
from src.crawlers.base import BaseCrawler
from src.crawlers.betalist_crawler import BetaListCrawler
from src.crawlers.f6s_crawler import F6SCrawler
from src.crawlers.launchingnext_crawler import LaunchingNextCrawler
from src.crawlers.producthunt_crawler import ProductHuntCrawler
from src.crawlers.saashub_crawler import SaaSHubCrawler
from src.crawlers.wellfound_crawler import WellfoundCrawler
from src.crawlers.yc_crawler import YCCrawler
from src.export.exporter import run_export
from src.pipeline.deduplicator import deduplicate
from src.pipeline.enricher import AIEnricher
from src.pipeline.normalizer import normalize_batch
from src.pipeline.validator import validate_batch

logger = get_logger(__name__)

CRAWLER_REGISTRY: dict[str, type[BaseCrawler]] = {
    "yc": YCCrawler,
    "producthunt": ProductHuntCrawler,
    "betalist": BetaListCrawler,
    "f6s": F6SCrawler,
    "wellfound": WellfoundCrawler,
    "saashub": SaaSHubCrawler,
    "launchingnext": LaunchingNextCrawler,
}


class PipelineOrchestrator:
    """Orchestrates the full data extraction pipeline."""

    def __init__(
        self,
        sources: list[str] | None = None,
        limit: int | None = None,
        skip_enrichment: bool = False,
    ):
        self.sources = sources or list(CRAWLER_REGISTRY.keys())
        self.limit = limit
        self.skip_enrichment = skip_enrichment

    async def run(self) -> tuple[list[StartupRecord], QualityReport]:
        """Execute the full pipeline."""
        started = datetime.utcnow()
        logger.info("pipeline.start", sources=self.sources, limit=self.limit)

        # ── Stage 1: Crawl ──────────────────────────────────────
        all_records: list[StartupRecord] = []
        crawl_results: list[CrawlResult] = []

        crawl_tasks = []
        crawlers: list[BaseCrawler] = []

        for source_name in self.sources:
            if source_name not in CRAWLER_REGISTRY:
                logger.warning("pipeline.unknown_source", source=source_name)
                continue

            crawler_cls = CRAWLER_REGISTRY[source_name]
            crawler = crawler_cls(limit=self.limit)
            crawlers.append(crawler)
            crawl_tasks.append(self._run_crawler(crawler))

        results = await asyncio.gather(*crawl_tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error("pipeline.crawl_error", error=str(result))
                continue
            if isinstance(result, CrawlResult):
                crawl_results.append(result)
                all_records.extend(result.records)

        # Cleanup crawlers
        for crawler in crawlers:
            try:
                if hasattr(crawler, "cleanup"):
                    await crawler.cleanup()
            except Exception as e:
                logger.warning("pipeline.cleanup_error", source=crawler.source.value, error=str(e))

        logger.info("pipeline.crawl_complete", total_raw=len(all_records))

        if not all_records:
            logger.warning("pipeline.no_records")
            return [], QualityReport(
                total_records=0, unique_records=0, duplicates_removed=0
            )

        # ── Stage 2: Normalize ──────────────────────────────────
        normalized = normalize_batch(all_records)

        # ── Stage 3: Validate ──────────────────────────────────
        valid_records, quality_report = validate_batch(normalized)

        # ── Stage 4: Deduplicate ────────────────────────────────
        unique_records, dupes_removed = deduplicate(valid_records)
        quality_report.duplicates_removed = dupes_removed
        quality_report.unique_records = len(unique_records)

        # ── Stage 5: Enrich (AI) ────────────────────────────────
        if not self.skip_enrichment:
            enricher = AIEnricher()
            unique_records = await enricher.enrich_batch(unique_records)

        # ── Stage 6: Export ─────────────────────────────────────
        exported_files = run_export(unique_records, quality_report)

        finished = datetime.utcnow()
        duration = (finished - started).total_seconds()

        # Print summary
        self._print_summary(crawl_results, quality_report, exported_files, duration)

        return unique_records, quality_report

    async def _run_crawler(self, crawler: BaseCrawler) -> CrawlResult:
        """Run a single crawler with error handling."""
        try:
            return await crawler.run()
        except Exception as e:
            logger.error("pipeline.crawler_failed", source=crawler.source.value, error=str(e))
            return CrawlResult(
                source=crawler.source,
                errors=[str(e)],
            )

    def _print_summary(
        self,
        crawl_results: list[CrawlResult],
        report: QualityReport,
        exported: list,
        duration: float,
    ) -> None:
        """Print a human-readable pipeline summary."""
        print("\n" + "=" * 60)
        print("  StartupScout — Pipeline Summary")
        print("=" * 60)

        print(f"\n⏱  Duration: {duration:.1f}s")
        print(f"📊 Total records: {report.total_records}")
        print(f"✅ Valid records: {report.unique_records}")
        print(f"🔁 Duplicates removed: {report.duplicates_removed}")
        print(f"📈 Overall completeness: {report.overall_completeness_pct:.1f}%")

        print("\n📁 Source breakdown:")
        for cr in crawl_results:
            status = "✅" if not cr.errors else "⚠️"
            print(f"   {status} {cr.source}: {cr.total_extracted} extracted, {len(cr.errors)} errors")

        if report.field_quality:
            print("\n📋 Field completeness:")
            for fq in report.field_quality:
                bar = "█" * int(fq.completeness_pct / 5) + "░" * (20 - int(fq.completeness_pct / 5))
                print(f"   {fq.field_name:<25} {bar} {fq.completeness_pct:>5.1f}%")

        if exported:
            print(f"\n📦 Exported to:")
            for path in exported:
                print(f"   → {path}")

        if report.anomalies:
            print(f"\n⚠️  Anomalies ({len(report.anomalies)}):")
            for anomaly in report.anomalies[:10]:
                print(f"   - {anomaly}")
            if len(report.anomalies) > 10:
                print(f"   ... and {len(report.anomalies) - 10} more")

        print("\n" + "=" * 60)
