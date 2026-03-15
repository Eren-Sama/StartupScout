"""Centralized configuration via Pydantic Settings."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env before any settings are instantiated
load_dotenv(override=True)


class CrawlerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CRAWLER_")

    concurrency: int = Field(default=5, ge=1, le=20)
    delay_min: float = Field(default=1.0, ge=0.1)
    delay_max: float = Field(default=3.0, ge=0.5)
    timeout: int = Field(default=30, ge=5)
    max_retries: int = Field(default=3, ge=0)


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GROQ_")

    api_key: SecretStr = SecretStr("")
    model: str = "llama-3.3-70b-versatile"
    max_tokens: int = 1024
    temperature: float = 0.3
    batch_size: int = 10
    rate_limit_rpm: int = 30

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key.get_secret_value())


class AlgoliaSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="YC_ALGOLIA_")

    app_id: str = "45BWZJ1SGC"
    api_key: SecretStr = SecretStr(
        "NzllNTY5MzJiZGM2OTY2ZTQwMDEzOTNhYWZiZGRjODlhYzVkNjBmOGRjNzJiMWM4"
        "ZTU0ZDlhYTZjOTJiMjlhMWFuYWx5dGljc1RhZ3M9eWNkYyZyZXN0cmljdEluZGlj"
        "ZXM9WUNDb21wYW55X3Byb2R1Y3Rpb24lMkNZQ0NvbXBhbnlfQnlfTGF1bmNoX0Rh"
        "dGVfcHJvZHVjdGlvbiZ0YWdGaWx0ZXJzPSU1QiUyMnljZGNfcHVibGljJTIyJTVE"
    )
    url: str = "https://45bwzj1sgc-dsn.algolia.net/1/indexes/*/queries"


class ExportSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EXPORT_")

    format: str = "csv,json"
    output_dir: Path = Path("./output")


class Settings(BaseSettings):
    """Root application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    log_level: str = "INFO"
    log_file: str = "./logs/startupscout.log"

    crawler: CrawlerSettings = Field(default_factory=CrawlerSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    algolia: AlgoliaSettings = Field(default_factory=AlgoliaSettings)
    export: ExportSettings = Field(default_factory=ExportSettings)


settings = Settings()
