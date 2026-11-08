from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

PROPERTY_TYPES = [
    "single_family",
    "multi_family",
    "condos",
    "townhomes",
    "duplex_triplex",
    "farm",
    "land",
    "mobile",
]


class Strategy(str, Enum):
    STR = "str"  # short-term / vacation rental
    LTR = "ltr"  # long-term rental, cash flow
    APPRECIATION = "appreciation"  # personal use + appreciation
    LAND = "land"  # land / development


class SearchQuery(BaseModel):
    """A structured search. Filters map 1:1 onto HomeHarvest's server-side filters."""

    location: str = Field(
        ..., description='City/state, ZIP, county or address, e.g. "Asheville, NC"'
    )
    property_types: list[str] | None = Field(
        None, description=f"Subset of {PROPERTY_TYPES}. null = all types"
    )
    price_min: int | None = None
    price_max: int | None = None
    beds_min: int | None = None
    beds_max: int | None = None
    baths_min: float | None = None
    sqft_min: int | None = None
    sqft_max: int | None = None
    lot_sqft_min: int | None = None
    lot_sqft_max: int | None = None
    year_built_min: int | None = None
    radius_miles: float | None = Field(None, description="Only valid when location is an address")
    past_days: int | None = Field(None, description="Only listings listed in the last N days")
    strategies: list[Strategy] = Field(
        default_factory=lambda: [Strategy.LTR, Strategy.APPRECIATION],
        description="What the buyer cares about; drives scoring and the analyst agent",
    )
    notes: str = Field("", description="Free-text wishes for the analyst (views, near hiking, ...)")
    limit: int = Field(200, ge=1, le=2000)

    def slug(self) -> str:
        base = "".join(c if c.isalnum() else "-" for c in self.location.lower())
        return "-".join(p for p in base.split("-") if p)[:40] or "search"


class Analysis(BaseModel):
    """Structured output of the analyst agent for one listing."""

    score: int = Field(..., ge=1, le=10, description="Overall opportunity score 1-10")
    best_strategy: Strategy
    thesis: str = Field(..., description="2-3 sentence investment thesis")
    upside: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    matches_notes: bool | None = Field(None, description="Does it match the buyer's notes?")
    questions_to_ask: list[str] = Field(default_factory=list)
