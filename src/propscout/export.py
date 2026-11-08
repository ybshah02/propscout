from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from propscout.pipeline import RunResult

KEY_COLUMNS = [
    "rank",
    "ai_score",
    "prescore",
    "formatted_address",
    "list_price",
    "beds",
    "full_baths",
    "half_baths",
    "sqft",
    "lot_sqft",
    "year_built",
    "style",
    "days_on_mls",
    "est_rent",
    "rent_method",
    "rent_confidence",
    "mortgage_mo",
    "cash_flow_mo",
    "cap_rate",
    "cash_on_cash",
    "gross_yield",
    "estimated_value",
    "value_gap_pct",
    "price_per_sqft_calc",
    "zip_median_ppsf",
    "ppsf_gap_pct",
    "hoa_fee",
    "tax",
    "ai_best_strategy",
    "ai_thesis",
    "ai_upside",
    "ai_risks",
    "ai_questions",
    "ai_matches_notes",
    "ai_error",
    "property_url",
    "zip_code",
    "county",
    "latitude",
    "longitude",
    "mls_id",
    "property_id",
    "list_date",
    "primary_photo",
]


def write_outputs(result: RunResult, out_dir: Path, all_columns: bool = False) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = out_dir / f"{stamp}_{result.query.slug()}"
    df = result.df
    cols = [c for c in KEY_COLUMNS if c in df.columns]
    if all_columns:
        cols += [c for c in df.columns if c not in cols]
    csv_path = base.with_suffix(".csv")
    df[cols].to_csv(csv_path, index=False)
    md_path = base.with_suffix(".md")
    md_path.write_text(render_markdown(result))
    return csv_path, md_path


def _m(v) -> str:
    return "—" if v is None or pd.isna(v) else f"${float(v):,.0f}"


def _p(v) -> str:
    return "—" if v is None or pd.isna(v) else f"{float(v) * 100:.1f}%"


def render_markdown(result: RunResult, top: int = 15) -> str:
    q = result.query
    lines = [
        f"# PropScout: {q.location}",
        "",
        f"- Generated: {datetime.now():%Y-%m-%d %H:%M}",
        f"- Strategies: {', '.join(s.value for s in q.strategies)}",
        f"- Filters: `{q.model_dump_json(exclude_none=True, exclude={'strategies', 'notes'})}`",
    ]
    if q.notes:
        lines.append(f"- Notes: {q.notes}")
    lines += [
        f"- Listings: {len(result.df)} · rent comps: {result.rent_comp_count} · "
        f"AI-analysed: {result.analyzed}",
    ]
    for w in result.warnings:
        lines.append(f"- ⚠️ {w}")
    lines += [
        "",
        "| # | AI | Pre | Address | Price | Bd/Ba | Sqft | Rent est | Cap | CF/mo | vs est. value |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    df = result.df.head(top)
    for _, r in df.iterrows():
        ai = "" if pd.isna(r.get("ai_score")) else int(r["ai_score"])
        lines.append(
            f"| {r['rank']} | {ai} | {r.get('prescore', '')} | "
            f"[{r.get('formatted_address', '')}]({r.get('property_url', '')}) | "
            f"{_m(r.get('list_price'))} | {r.get('beds', '')}/{r.get('full_baths', '')} | "
            f"{r.get('sqft', '')} | {_m(r.get('est_rent'))} | {_p(r.get('cap_rate'))} | "
            f"{_m(r.get('cash_flow_mo'))} | {_p(r.get('value_gap_pct'))} |"
        )
    analysed = df[df["ai_thesis"].notna()] if "ai_thesis" in df.columns else df.iloc[0:0]
    if len(analysed):
        lines += ["", "## Analyst notes", ""]
        for _, r in analysed.iterrows():
            lines += [
                f"### {r['rank']}. {r.get('formatted_address', '')} — {int(r['ai_score'])}/10 "
                f"({r.get('ai_best_strategy', '')})",
                "",
                str(r["ai_thesis"]),
                "",
                f"- **Upside:** {r.get('ai_upside') or '—'}",
                f"- **Risks:** {r.get('ai_risks') or '—'}",
                f"- **Ask the agent:** {r.get('ai_questions') or '—'}",
                "",
            ]
    lines += [
        "",
        "_Cap rate / cash flow assume long-term rental at the comp-based rent estimate and the "
        "financing assumptions in your env. Not financial advice — verify everything._",
    ]
    return "\n".join(lines)
