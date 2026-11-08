"""search -> comps -> underwriting -> prescore -> LLM analysis -> ranked DataFrame."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from propscout.agents.analyst import analyze_many
from propscout.agents.llm import LLM
from propscout.analysis.comps import RentComps, SaleComps
from propscout.analysis.finance import underwrite
from propscout.analysis.scoring import prescore
from propscout.config import Settings
from propscout.models import Analysis, SearchQuery
from propscout.sources.base import Source

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    query: SearchQuery
    df: pd.DataFrame
    warnings: list[str] = field(default_factory=list)
    rent_comp_count: int = 0
    analyzed: int = 0


def _f(v) -> float | None:
    try:
        x = float(v)
        return None if pd.isna(x) else x
    except (TypeError, ValueError):
        return None


def rent_confidence(method: str) -> str:
    """high = same ZIP + beds, medium = same beds in area, low = ZIP houses of any size."""
    if method.startswith("zip+beds"):
        return "high"
    if method.startswith("area+beds"):
        return "medium"
    if method.startswith("zip houses"):
        return "low"
    return "n/a" if method == "not_applicable" else "none"


def enrich(df: pd.DataFrame, rents: RentComps, sales: SaleComps, s: Settings) -> pd.DataFrame:
    """Add rent estimate, underwriting and value-gap columns."""
    rows = []
    for _, r in df.iterrows():
        price = _f(r.get("list_price"))
        sqft = _f(r.get("sqft"))
        beds = _f(r.get("beds"))
        if str(r.get("style", "")).upper() == "LAND" or (beds is None and sqft is None):
            rent, method = None, "not_applicable"  # vacant land: no rental income to underwrite
        else:
            rent, method = rents.estimate(r.get("zip_code"), beds)
        u = underwrite(
            price, rent, s, annual_tax=_f(r.get("tax")), hoa_monthly=_f(r.get("hoa_fee"))
        )
        ppsf = price / sqft if sqft and sqft > 0 else None
        zip_ppsf = sales.median_ppsf(r.get("zip_code"))
        est_value = _f(r.get("estimated_value"))
        rows.append(
            {
                "est_rent": u.rent,
                "rent_method": method,
                "rent_confidence": rent_confidence(method),
                "mortgage_mo": round(u.mortgage, 2),
                "cash_needed": round(u.cash_needed, 2),
                "noi_annual": u.noi_annual,
                "cap_rate": u.cap_rate,
                "cash_flow_mo": u.cash_flow_mo,
                "cash_on_cash": u.cash_on_cash,
                "gross_yield": u.gross_yield,
                "price_per_sqft_calc": ppsf,
                "zip_median_ppsf": zip_ppsf,
                "ppsf_gap_pct": (zip_ppsf - ppsf) / zip_ppsf if ppsf and zip_ppsf else None,
                "value_gap_pct": (est_value - price) / price if est_value and price else None,
            }
        )
    extra = pd.DataFrame(rows, index=df.index)
    for c in extra.columns:
        if c not in ("rent_method", "rent_confidence"):
            extra[c] = pd.to_numeric(extra[c], errors="coerce").astype("float64")
    return pd.concat([df, extra], axis=1)


def _apply_analyses(df: pd.DataFrame, results: dict[int, Analysis | Exception]) -> pd.DataFrame:
    cols = {
        "ai_score": {},
        "ai_best_strategy": {},
        "ai_thesis": {},
        "ai_upside": {},
        "ai_risks": {},
        "ai_questions": {},
        "ai_matches_notes": {},
        "ai_error": {},
    }
    for idx, a in results.items():
        if isinstance(a, Exception):
            cols["ai_error"][idx] = str(a)[:300]
            continue
        cols["ai_score"][idx] = a.score
        cols["ai_best_strategy"][idx] = a.best_strategy.value
        cols["ai_thesis"][idx] = a.thesis
        cols["ai_upside"][idx] = "; ".join(a.upside)
        cols["ai_risks"][idx] = "; ".join(a.risks)
        cols["ai_questions"][idx] = "; ".join(a.questions_to_ask)
        cols["ai_matches_notes"][idx] = a.matches_notes
    for name, values in cols.items():
        df[name] = pd.Series(values, dtype="object").reindex(df.index)
    df["ai_score"] = pd.to_numeric(df["ai_score"], errors="coerce")
    return df


def run(
    query: SearchQuery,
    source: Source,
    settings: Settings,
    llm: LLM | None = None,
    analyze_top: int = 10,
    on_step: Callable[[str], None] = lambda msg: None,
) -> RunResult:
    warnings: list[str] = []

    on_step(f"Searching {source.name} for listings in {query.location}…")
    listings = source.search(query)
    if listings.empty:
        return RunResult(query, listings, ["No listings matched the search."])
    if "property_id" in listings.columns:
        listings = listings.drop_duplicates(subset="property_id")
    listings = listings[pd.to_numeric(listings["list_price"], errors="coerce") > 0].reset_index(
        drop=True
    )
    on_step(f"Found {len(listings)} listings")

    on_step("Fetching rent comps…")
    try:
        rents = RentComps(source.rent_comps(query))
    except Exception as exc:
        warnings.append(f"Rent comps unavailable: {exc}")
        rents = RentComps(pd.DataFrame())
    on_step("Fetching sold comps (last 180 days)…")
    try:
        sales = SaleComps(source.sold_comps(query))
    except Exception as exc:
        warnings.append(f"Sold comps unavailable: {exc}")
        sales = SaleComps(pd.DataFrame())

    on_step("Underwriting + prescoring…")
    df = enrich(listings, rents, sales, settings)
    rentable = df["rent_confidence"] != "n/a"
    weak = df.loc[rentable, "rent_confidence"].isin(["low", "none"]).mean() if rentable.any() else 0
    if weak > 0.5:
        warnings.append(
            f"Thin rental market: {weak:.0%} of rent estimates are low-confidence or missing "
            f"({len(rents)} rent comps). Treat cap rate / cash flow as rough."
        )
    df["prescore"] = prescore(df, query.strategies)
    df = df.sort_values("prescore", ascending=False, na_position="last").reset_index(drop=True)

    analyzed = 0
    if llm is not None and analyze_top > 0:
        top = df.head(analyze_top)
        on_step(f"Analysing top {len(top)} listings with the LLM…")
        results = analyze_many(llm, query, top, concurrency=settings.llm_concurrency)
        df = _apply_analyses(df, results)
        analyzed = sum(1 for v in results.values() if not isinstance(v, Exception))
        failed = len(results) - analyzed
        if failed:
            warnings.append(f"{failed} LLM analyses failed (see ai_error column)")
        df = df.sort_values(
            ["ai_score", "prescore"], ascending=[False, False], na_position="last"
        ).reset_index(drop=True)

    df.insert(0, "rank", range(1, len(df) + 1))
    return RunResult(query, df, warnings, rent_comp_count=len(rents), analyzed=analyzed)
