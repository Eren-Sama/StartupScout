"""StartupScout CLI entry point with interactive mode."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from src.core.config import settings
from src.core.logging import setup_logging
from src.orchestrator import CRAWLER_REGISTRY, PipelineOrchestrator


def interactive_mode() -> None:
    """Interactive prompt-based mode for users."""
    print("\n" + "=" * 50)
    print("  🔍 StartupScout — Interactive Mode")
    print("=" * 50)

    # Step 1: Choose sources
    print("\n📡 Available sources:\n")
    source_list = list(CRAWLER_REGISTRY.keys())
    for i, name in enumerate(source_list, 1):
        print(f"  {i}. {name:<15} → {CRAWLER_REGISTRY[name].base_url}")
    print(f"  {len(source_list) + 1}. all             → All sources")

    print()
    source_input = input("Select sources (comma-separated numbers, or 'all'): ").strip()

    if source_input.lower() == "all" or source_input == str(len(source_list) + 1):
        sources = source_list
    else:
        try:
            indices = [int(x.strip()) for x in source_input.split(",")]
            sources = [source_list[i - 1] for i in indices if 1 <= i <= len(source_list)]
        except (ValueError, IndexError):
            print("❌ Invalid selection. Using 'yc' as default.")
            sources = ["yc"]

    if not sources:
        sources = ["yc"]

    print(f"  ✅ Selected: {', '.join(sources)}")

    # Step 2: How many companies
    print()
    limit_input = input("How many companies to scrape per source? (e.g. 10, 50, 100): ").strip()
    try:
        limit = int(limit_input)
        if limit < 1:
            limit = 10
    except ValueError:
        print("  ⚠️  Invalid number. Using 10 as default.")
        limit = 10

    print(f"  ✅ Limit: {limit} per source")

    # Step 3: Output format
    print()
    print("💾 Output format:")
    print("  1. CSV only")
    print("  2. JSON only")
    print("  3. Both CSV and JSON")
    print()
    format_input = input("Select format (1/2/3): ").strip()

    format_map = {"1": "csv", "2": "json", "3": "csv,json"}
    export_format = format_map.get(format_input, "csv,json")

    if format_input not in format_map:
        print("  ⚠️  Invalid choice. Using both CSV and JSON.")

    print(f"  ✅ Format: {export_format}")

    # Step 4: Output directory
    print()
    output_input = input(f"Output directory (press Enter for './output'): ").strip()
    output_dir = Path(output_input).resolve() if output_input else Path("./output").resolve()
    print(f"  ✅ Output: {output_dir}")

    # Step 5: AI enrichment
    print()
    if settings.llm.is_configured:
        enrich_input = input("Enable AI enrichment with Groq? (y/n, default: y): ").strip().lower()
        skip_enrichment = enrich_input == "n"
    else:
        print("  ℹ️  GROQ_API_KEY not set — AI enrichment disabled")
        skip_enrichment = True

    enrich_label = "disabled" if skip_enrichment else "enabled"
    print(f"  ✅ AI Enrichment: {enrich_label}")

    # Apply settings
    settings.export.format = export_format
    settings.export.output_dir = output_dir

    # Confirm and run
    print("\n" + "-" * 50)
    print(f"  Sources:    {', '.join(sources)}")
    print(f"  Limit:      {limit} per source")
    print(f"  Format:     {export_format}")
    print(f"  Output:     {output_dir}")
    print(f"  Enrichment: {enrich_label}")
    print("-" * 50)
    print()
    confirm = input("🚀 Start scraping? (y/n): ").strip().lower()

    if confirm != "y" and confirm != "yes" and confirm != "":
        print("Cancelled.")
        return

    print()
    orchestrator = PipelineOrchestrator(
        sources=sources,
        limit=limit,
        skip_enrichment=skip_enrichment,
    )

    records, report = asyncio.run(orchestrator.run())

    if not records:
        print("\n⚠️  No records extracted. Check logs for details.")
        sys.exit(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="startupscout",
        description="🔍 StartupScout — Production-grade startup data extraction platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main                           (interactive mode)
  python -m src.main run --source yc --limit 10
  python -m src.main run --source all --limit 20 --skip-enrichment
  python -m src.main run --output ./data
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run command — full pipeline (CLI flags)
    run_parser = subparsers.add_parser("run", help="Run the full extraction pipeline")
    run_parser.add_argument(
        "--source",
        type=str,
        default="all",
        help=f"Comma-separated sources: {', '.join(CRAWLER_REGISTRY.keys())}, or 'all' (default: all)",
    )
    run_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max records to extract per source (default: unlimited)",
    )
    run_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output directory (default: from config)",
    )
    run_parser.add_argument(
        "--format",
        type=str,
        default=None,
        help="Output format: csv, json, or csv,json (default: from config)",
    )
    run_parser.add_argument(
        "--skip-enrichment",
        action="store_true",
        help="Skip the AI enrichment stage",
    )

    # list command
    subparsers.add_parser("sources", help="List available data sources")

    return parser.parse_args()


def main() -> None:
    setup_logging()

    args = parse_args()

    # No command = interactive mode
    if not args.command:
        interactive_mode()
        return

    if args.command == "sources":
        print("\n🔍 Available data sources:\n")
        for name, cls in CRAWLER_REGISTRY.items():
            print(f"  • {name:<15} → {cls.base_url}")
        print(f"\n  Total: {len(CRAWLER_REGISTRY)} sources")
        return

    if args.command == "run":
        # Parse sources
        if args.source == "all":
            sources = list(CRAWLER_REGISTRY.keys())
        else:
            sources = [s.strip() for s in args.source.split(",")]
            invalid = [s for s in sources if s not in CRAWLER_REGISTRY]
            if invalid:
                print(f"❌ Unknown sources: {', '.join(invalid)}")
                print(f"   Available: {', '.join(CRAWLER_REGISTRY.keys())}")
                sys.exit(1)

        # Override settings from CLI flags
        if args.output:
            settings.export.output_dir = Path(args.output).resolve()
        if args.format:
            settings.export.format = args.format

        orchestrator = PipelineOrchestrator(
            sources=sources,
            limit=args.limit,
            skip_enrichment=args.skip_enrichment,
        )

        print("\n🚀 StartupScout — Starting extraction pipeline")
        print(f"   Sources: {', '.join(sources)}")
        print(f"   Limit: {args.limit or 'unlimited'} per source")
        print(f"   Format: {settings.export.format}")
        print(f"   Enrichment: {'enabled' if not args.skip_enrichment else 'disabled'}")
        print(f"   Output: {settings.export.output_dir}\n")

        records, report = asyncio.run(orchestrator.run())

        if not records:
            print("\n⚠️  No records extracted. Check logs for details.")
            sys.exit(1)

        sys.exit(0)


if __name__ == "__main__":
    main()
