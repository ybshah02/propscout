import pandas as pd

from propscout.analysis.comps import RentComps, SaleComps
from propscout.analysis.scoring import prescore
from propscout.models import Strategy


def rentals():
    return pd.DataFrame(
        {
            "zip_code": ["28801"] * 4 + ["28806"] * 3 + ["28806"],
            "beds": [3, 3, 3, pd.NA, 2, 2, 2, pd.NA],
            "list_price": [2000, 2200, 2400, pd.NA, 1500, 1600, 1700, pd.NA],
            "list_price_min": [pd.NA] * 3 + [1000, pd.NA, pd.NA, pd.NA, 100],
            "list_price_max": [pd.NA] * 3 + [1400, pd.NA, pd.NA, pd.NA, 120],
            "style": ["SINGLE_FAMILY"] * 3 + ["APARTMENT"] + ["SINGLE_FAMILY"] * 3 + ["APARTMENT"],
        }
    )


def test_rent_zip_beds_median():
    rc = RentComps(rentals())
    assert rc.estimate("28801", 3) == (2200.0, "zip+beds (n=3)")


def test_rent_falls_back_to_area_beds():
    rc = RentComps(rentals())
    rent, method = rc.estimate("99999", 2)
    assert rent == 1600.0 and method.startswith("area+beds")


def test_rent_falls_back_to_zip_houses_when_beds_unknown():
    rc = RentComps(rentals())
    rent, method = rc.estimate("28806", None)
    assert rent == 1600.0 and method.startswith("zip houses")


def test_rent_insufficient_and_bogus_filtered():
    rc = RentComps(rentals())
    assert len(rc) == 7  # the $110 midpoint row is dropped
    assert rc.estimate("12345", 5) == (None, "insufficient_comps")
    assert RentComps(pd.DataFrame()).estimate("1", 1) == (None, "no_rent_comps")


def test_sale_comps_zip_and_area():
    sold = pd.DataFrame(
        {
            "zip_code": ["1"] * 3 + ["2"],
            "sold_price": [200_000, 300_000, 400_000, 900_000],
            "sqft": [1000, 1000, 1000, 1000],
        }
    )
    sc = SaleComps(sold)
    assert sc.median_ppsf("1") == 300
    assert sc.median_ppsf("2") == 350  # only 1 sample in zip 2 -> area median of all 4


def test_prescore_prefers_better_deal_and_handles_missing():
    df = pd.DataFrame(
        {
            "list_price": [300_000, 300_000, 300_000],
            "cap_rate": [0.07, 0.01, None],
            "cash_on_cash": [0.05, -0.08, None],
            "value_gap_pct": [0.10, -0.05, None],
            "ppsf_gap_pct": [0.2, -0.2, None],
            "days_on_mls": [60, 5, None],
            "lot_sqft": [20000, 5000, None],
        }
    )
    s = prescore(df, [Strategy.LTR])
    assert s[0] > s[1]
    assert 0 <= s[1] <= 100
    # Row 2 only has the lot-rank signal (unused by LTR) -> NaN rather than 0
    assert pd.isna(s[2])
