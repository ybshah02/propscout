"""Natural language -> SearchQuery."""

from __future__ import annotations

from propscout.agents.llm import LLM
from propscout.models import PROPERTY_TYPES, SearchQuery

SYSTEM = f"""You convert a home buyer's request into a structured real estate search.
Rules:
- location: the most specific searchable place ("City, ST", ZIP, or county). Use 2-letter state codes.
- Prices in whole US dollars ("500k" -> 500000). Lot sizes in square feet (1 acre = 43560 sqft).
- property_types must be a subset of {PROPERTY_TYPES}. A "cabin" or "house" is single_family;
  "land"/"lot"/"acreage" is land (+ farm if rural acreage). Leave null if unspecified.
- strategies: "str" (Airbnb/vacation rental), "ltr" (long-term rental/cash flow),
  "appreciation" (personal use / long-term growth), "land" (land/development). Pick all that apply;
  default to ["ltr", "appreciation"] if unclear.
- Put soft preferences that can't be filtered (views, near hiking, quiet, walkable) into notes.
- Leave any filter null if the user didn't specify it. Never invent constraints."""


def parse_prompt(llm: LLM, prompt: str) -> SearchQuery:
    return llm.complete_json(SYSTEM, prompt, SearchQuery)
