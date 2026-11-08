"""Deterministic underwriting math. The LLM never does arithmetic; it reads these numbers."""

from __future__ import annotations

import math
from dataclasses import dataclass

from propscout.config import Settings


def monthly_payment(principal: float, annual_rate: float, years: int) -> float:
    if principal <= 0:
        return 0.0
    n = years * 12
    r = annual_rate / 12
    if r == 0:
        return principal / n
    return principal * r * (1 + r) ** n / ((1 + r) ** n - 1)


def _ok(x) -> bool:
    try:
        return x is not None and not math.isnan(float(x))
    except (TypeError, ValueError):
        return False


@dataclass
class Underwriting:
    mortgage: float
    taxes_mo: float
    insurance_mo: float
    hoa_mo: float
    cash_needed: float
    rent: float | None = None
    noi_annual: float | None = None
    cap_rate: float | None = None
    cash_flow_mo: float | None = None
    cash_on_cash: float | None = None
    gross_yield: float | None = None

    def as_dict(self) -> dict:
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in self.__dict__.items()}


def underwrite(
    price: float,
    rent: float | None,
    s: Settings,
    annual_tax: float | None = None,
    hoa_monthly: float | None = None,
) -> Underwriting:
    """Long-term-rental underwriting for a purchase at `price` with monthly market `rent`."""
    down = price * s.down_payment_pct
    mortgage = monthly_payment(price - down, s.interest_rate, s.loan_years)
    taxes_mo = (
        annual_tax if _ok(annual_tax) and annual_tax > 0 else price * s.property_tax_pct
    ) / 12
    insurance_mo = price * s.insurance_pct / 12
    hoa_mo = float(hoa_monthly) if _ok(hoa_monthly) else 0.0
    cash_needed = down + price * s.closing_cost_pct
    u = Underwriting(mortgage, taxes_mo, insurance_mo, hoa_mo, cash_needed)
    if not _ok(rent) or rent <= 0 or price <= 0:
        return u
    gross = rent * 12
    effective = gross * (1 - s.vacancy_pct)
    variable = gross * (s.maintenance_pct + s.capex_pct + s.management_pct)
    fixed = (taxes_mo + insurance_mo + hoa_mo) * 12
    noi = effective - variable - fixed
    u.rent = float(rent)
    u.noi_annual = noi
    u.cap_rate = noi / price
    u.cash_flow_mo = noi / 12 - mortgage
    u.cash_on_cash = (u.cash_flow_mo * 12) / cash_needed if cash_needed else None
    u.gross_yield = gross / price
    return u
