"""Strategy-weighted deterministic prescore (0-100) used to pick which listings the LLM analyses."""

from __future__ import annotations

import pandas as pd

from propscout.models import Strategy

# signal -> weight, per strategy
WEIGHTS: dict[Strategy, dict[str, float]] = {
    Strategy.LTR: {"cap": 3, "coc": 3, "value_gap": 2, "ppsf_gap": 2, "dom": 1},
    # STR uses LTR economics as a proxy until STR comps land (V2)
    Strategy.STR: {"cap": 2, "coc": 2, "value_gap": 2, "ppsf_gap": 2, "dom": 1, "lot": 1},
    Strategy.APPRECIATION: {"value_gap": 3, "ppsf_gap": 3, "dom": 2, "cap": 1, "lot": 1},
    Strategy.LAND: {"lot": 4, "value_gap": 2, "dom": 2, "ppsf_gap": 1},
}


def _scale(s: pd.Series, lo: float, hi: float) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce").astype("float64")
    return ((s.clip(lo, hi) - lo) / (hi - lo)).astype("float64")


def signals(df: pd.DataFrame) -> pd.DataFrame:
    """Each signal in [0, 1] (higher = better) or NaN when unknown."""

    def col(name: str) -> pd.Series:
        if name in df.columns:
            return pd.to_numeric(df[name], errors="coerce").astype("float64")
        return pd.Series(float("nan"), index=df.index, dtype="float64")

    price = col("list_price")
    lot_per_dollar = col("lot_sqft") / price
    return pd.DataFrame(
        {
            "cap": _scale(col("cap_rate"), 0.0, 0.08),
            "coc": _scale(col("cash_on_cash"), -0.10, 0.10),
            "value_gap": _scale(col("value_gap_pct"), -0.10, 0.15),
            "ppsf_gap": _scale(col("ppsf_gap_pct"), -0.30, 0.30),
            "dom": _scale(col("days_on_mls"), 0, 120),
            "lot": lot_per_dollar.rank(pct=True),
        },
        index=df.index,
    )


def prescore(df: pd.DataFrame, strategies: list[Strategy]) -> pd.Series:
    weights: dict[str, float] = {}
    for strat in strategies or [Strategy.LTR]:
        for k, w in WEIGHTS[strat].items():
            weights[k] = weights.get(k, 0) + w
    sig = signals(df)
    num = pd.Series(0.0, index=df.index)
    den = pd.Series(0.0, index=df.index)
    for k, w in weights.items():
        present = sig[k].notna()
        num = num + sig[k].fillna(0) * w
        den = den + present.astype(float) * w
    # Missing signals are excluded rather than counted as zero
    score = (num / den.where(den > 0)) * 100
    return score.round(1)
