from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from env vars / .env so the same code runs locally and on Railway."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # LLM
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    model: str = Field("deepseek/deepseek-v4.1-flash", alias="PROPSCOUT_MODEL")
    fallback_models: str = Field(
        "qwen/qwen3.8-flash,google/gemini-2.5-flash-lite", alias="PROPSCOUT_FALLBACK_MODELS"
    )
    llm_concurrency: int = Field(6, alias="PROPSCOUT_LLM_CONCURRENCY")

    # Notifications
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Scraping
    proxy: str | None = Field(None, alias="PROPSCOUT_PROXY")

    # Finance assumptions
    interest_rate: float = Field(0.065, alias="PROPSCOUT_INTEREST_RATE")
    down_payment_pct: float = Field(0.20, alias="PROPSCOUT_DOWN_PAYMENT_PCT")
    loan_years: int = Field(30, alias="PROPSCOUT_LOAN_YEARS")
    closing_cost_pct: float = Field(0.03, alias="PROPSCOUT_CLOSING_COST_PCT")
    insurance_pct: float = Field(0.006, alias="PROPSCOUT_INSURANCE_PCT")
    property_tax_pct: float = Field(0.011, alias="PROPSCOUT_PROPERTY_TAX_PCT")
    vacancy_pct: float = Field(0.06, alias="PROPSCOUT_VACANCY_PCT")
    maintenance_pct: float = Field(0.08, alias="PROPSCOUT_MAINTENANCE_PCT")
    capex_pct: float = Field(0.05, alias="PROPSCOUT_CAPEX_PCT")
    management_pct: float = Field(0.08, alias="PROPSCOUT_MANAGEMENT_PCT")

    @property
    def fallback_model_list(self) -> list[str]:
        return [m.strip() for m in self.fallback_models.split(",") if m.strip()]

    @property
    def llm_enabled(self) -> bool:
        return bool(self.openrouter_api_key)

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)


@lru_cache
def get_settings() -> Settings:
    return Settings()
