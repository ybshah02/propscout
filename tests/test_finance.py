import math

import pytest

from propscout.analysis.finance import monthly_payment, underwrite
from propscout.config import Settings


def settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_monthly_payment_matches_known_value():
    # $400k, 6.5%, 30y -> ~$2,528.27
    assert monthly_payment(400_000, 0.065, 30) == pytest.approx(2528.27, abs=0.05)


def test_monthly_payment_zero_rate():
    assert monthly_payment(360_000, 0.0, 30) == pytest.approx(1000.0)


def test_underwrite_without_rent_has_no_return_metrics():
    u = underwrite(300_000, None, settings())
    assert u.cap_rate is None and u.cash_flow_mo is None
    assert u.cash_needed == pytest.approx(300_000 * 0.23)


def test_underwrite_with_rent():
    s = settings()
    u = underwrite(300_000, 2500, s, annual_tax=3000, hoa_monthly=50)
    gross = 2500 * 12
    noi = (
        gross * (1 - s.vacancy_pct) - gross * (0.08 + 0.05 + 0.08) - (3000 + 300_000 * 0.006 + 600)
    )
    assert u.noi_annual == pytest.approx(noi)
    assert u.cap_rate == pytest.approx(noi / 300_000)
    assert u.cash_flow_mo == pytest.approx(noi / 12 - u.mortgage)
    assert u.gross_yield == pytest.approx(0.10)


def test_underwrite_ignores_nan_tax():
    u = underwrite(200_000, 1500, settings(), annual_tax=math.nan)
    assert u.taxes_mo == pytest.approx(200_000 * 0.011 / 12)
