"""Rent and sale comps built from scraped listings, with an explicit fallback chain.

We never invent numbers: if there's not enough comp data, the estimate is None.
"""

from __future__ import annotations

import math

import pandas as pd

MIN_SAMPLES = 3
HOUSE_STYLES = {"SINGLE_FAMILY", "TOWNHOMES", "TOWNHOUSE", "DUPLEX_TRIPLEX", "MULTI_FAMILY"}


def _num(series: pd.Series | None, index: pd.Index) -> pd.Series:
    if series is None:
        return pd.Series(float("nan"), index=index, dtype="float64")
    return pd.to_numeric(series, errors="coerce").astype("float64")


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    return _num(df[name] if name in df.columns else None, df.index)


def _zip(series: pd.Series) -> pd.Series:
    return series.astype("string").str.slice(0, 5)


def _valid(x: float | None) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


class RentComps:
    """Median monthly rent lookups from for-rent listings."""

    def __init__(self, rentals: pd.DataFrame):
        if rentals is None or rentals.empty:
            self.df = pd.DataFrame(columns=["zip", "beds", "rent", "style"])
            return
        price = _col(rentals, "list_price")
        lo, hi = _col(rentals, "list_price_min"), _col(rentals, "list_price_max")
        midpoint = (lo + hi) / 2
        rent = price.fillna(midpoint).fillna(lo).fillna(hi)
        df = pd.DataFrame(
            {
                "zip": _zip(
                    rentals.get("zip_code", pd.Series(index=rentals.index, dtype="string"))
                ),
                "beds": _col(rentals, "beds"),
                "rent": rent,
                "style": rentals.get("style", pd.Series("", index=rentals.index)).astype("string"),
            }
        )
        # Drop obviously bogus rents (parking spots, typos, luxury outliers)
        self.df = df[(df["rent"] >= 300) & (df["rent"] <= 30000)].reset_index(drop=True)

    def __len__(self) -> int:
        return len(self.df)

    def _median(self, mask: pd.Series) -> tuple[float | None, int]:
        vals = self.df.loc[mask, "rent"].dropna()
        if len(vals) >= MIN_SAMPLES:
            return float(vals.median()), len(vals)
        return None, len(vals)

    def estimate(self, zip_code: str | None, beds: float | None) -> tuple[float | None, str]:
        """Return (monthly_rent, method). method explains which fallback produced it."""
        if self.df.empty:
            return None, "no_rent_comps"
        z = str(zip_code)[:5] if zip_code is not None and str(zip_code) != "<NA>" else None
        b = beds if _valid(beds) else None
        df = self.df
        if z and b is not None:
            v, n = self._median((df["zip"] == z) & (df["beds"] == b))
            if v:
                return v, f"zip+beds (n={n})"
        if b is not None:
            v, n = self._median(df["beds"] == b)
            if v:
                return v, f"area+beds (n={n})"
        if z:
            v, n = self._median((df["zip"] == z) & df["style"].isin(HOUSE_STYLES))
            if v:
                return v, f"zip houses (n={n})"
        return None, "insufficient_comps"


class SaleComps:
    """Median sold $/sqft by ZIP (falls back to the whole search area)."""

    def __init__(self, sold: pd.DataFrame):
        if sold is None or sold.empty:
            self.by_zip: dict[str, float] = {}
            self.area: float | None = None
            return
        price = _col(sold, "sold_price").fillna(_col(sold, "list_price"))
        sqft = _col(sold, "sqft")
        ppsf = (price / sqft).where((sqft > 300) & (price > 10000))
        df = pd.DataFrame(
            {"zip": _zip(sold.get("zip_code", pd.Series(dtype="string"))), "ppsf": ppsf}
        )
        df = df.dropna(subset=["ppsf"])
        counts = df.groupby("zip")["ppsf"].count()
        med = df.groupby("zip")["ppsf"].median()
        self.by_zip = {z: float(med[z]) for z in med.index if counts[z] >= MIN_SAMPLES}
        self.area = float(df["ppsf"].median()) if len(df) >= MIN_SAMPLES else None

    def median_ppsf(self, zip_code: str | None) -> float | None:
        if zip_code is not None:
            v = self.by_zip.get(str(zip_code)[:5])
            if v:
                return v
        return self.area
