"""Analyst agent: writes a short structured investment memo per listing from precomputed facts."""

from __future__ import annotations

import json
import logging
import math
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from propscout.agents.llm import LLM
from propscout.models import Analysis, SearchQuery

log = logging.getLogger(__name__)

SYSTEM = """You are a pragmatic real estate investment analyst. You receive facts about ONE listing
(already-computed financial metrics included) plus the buyer's goals. Judge it as an opportunity.
Rules:
- Use only the facts given. Do not recompute or invent numbers; cite the provided ones.
- If rent/comps are missing, say the economics are unverified rather than guessing.
- Consider the buyer's strategies: str (Airbnb/vacation rental: location appeal, amenities,
  likely local STR rules/HOA restrictions), ltr (cash flow), appreciation (value vs. market, area),
  land (acreage, buildability, access, utilities).
- Read the listing description for upside (ADU potential, views, renovation room, acreage) and red
  flags (as-is, cash only, flood, foundation, septic, HOA rental bans, steep road).
- score: 1-10 where 5 = average listing, 8+ = clearly worth a call today.
- Be concise: thesis <= 3 sentences, each list <= 4 short items."""

FACT_COLS = [
    "formatted_address",
    "style",
    "list_price",
    "beds",
    "full_baths",
    "half_baths",
    "sqft",
    "lot_sqft",
    "year_built",
    "days_on_mls",
    "hoa_fee",
    "tax",
    "estimated_value",
    "value_gap_pct",
    "price_per_sqft",
    "zip_median_ppsf",
    "ppsf_gap_pct",
    "est_rent",
    "rent_method",
    "rent_confidence",
    "mortgage_mo",
    "cash_needed",
    "noi_annual",
    "cap_rate",
    "cash_flow_mo",
    "cash_on_cash",
    "gross_yield",
    "last_sold_date",
    "last_sold_price",
    "new_construction",
    "county",
    "prescore",
]


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float):
        return None if math.isnan(v) else round(v, 4)
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "item"):
        return v.item()
    return str(v) if not isinstance(v, (int, float, bool, str)) else v


def listing_facts(row: pd.Series) -> dict:
    facts = {c: _clean(row.get(c)) for c in FACT_COLS if c in row.index}
    facts = {k: v for k, v in facts.items() if v is not None}
    desc = row.get("text")
    if isinstance(desc, str) and desc:
        facts["description"] = desc[:1500]
    return facts


def analyze_one(llm: LLM, query: SearchQuery, row: pd.Series) -> Analysis:
    user = json.dumps(
        {
            "buyer": {
                "strategies": [s.value for s in query.strategies],
                "notes": query.notes or None,
                "search_area": query.location,
            },
            "listing": listing_facts(row),
        },
        default=str,
    )
    return llm.complete_json(SYSTEM, user, Analysis)


def analyze_many(
    llm: LLM, query: SearchQuery, df: pd.DataFrame, concurrency: int = 6
) -> dict[int, Analysis | Exception]:
    """Analyse each row in parallel. Returns {index: Analysis | Exception}; failures don't abort."""

    def run(idx):
        try:
            return idx, analyze_one(llm, query, df.loc[idx])
        except Exception as exc:  # keep going; report per-row errors
            log.warning("analysis failed for row %s: %s", idx, exc)
            return idx, exc

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict(pool.map(run, list(df.index)))
