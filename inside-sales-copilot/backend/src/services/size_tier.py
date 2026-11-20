"""Company size tier (requirements R3.5 to R3.8, design 8.3). Plain code, never the model.

Enterprise: more than 5,000 employees OR more than $1B revenue. Otherwise by employees:
Mid-market 500 to 5,000, SMB 50 to 499, Boutique below 50. Unknown when employees are not
known and revenue does not make the company Enterprise.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

from ..lib import constants as c


def _clean(value: Any) -> float | None:
    """A usable positive-or-zero number, or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if math.isnan(value) or math.isinf(value) or value < 0:
        return None
    return float(value)


def _money(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:,.2f}B".replace(".00B", "B")
    return f"${value / 1_000_000:,.0f}M"


def compute_size_tier(
    employees: Any,
    revenue_usd: Any,
    source_urls: Sequence[str] = (),
) -> dict[str, Any]:
    """Return the `sizeTier` object of the research result (design 5.4)."""
    emp = _clean(employees)
    rev = _clean(revenue_usd)

    big_by_employees = emp is not None and emp > c.ENTERPRISE_EMPLOYEES_ABOVE
    big_by_revenue = rev is not None and rev > c.ENTERPRISE_REVENUE_USD_ABOVE

    if big_by_employees or big_by_revenue:
        tier = "Enterprise"
        reasons = []
        if big_by_employees:
            reasons.append(f"{int(emp):,} employees is more than {c.ENTERPRISE_EMPLOYEES_ABOVE:,}")
        if big_by_revenue:
            reasons.append(f"revenue of {_money(rev)} is more than $1B")
        rule = "Enterprise: " + " and ".join(reasons)
        # Both numbers are shown when they point to different tiers (R3.8).
        if emp is not None and not big_by_employees:
            rule += f" (employees: {int(emp):,}, which alone would be {_tier_by_employees(emp)})"
        if rev is not None and not big_by_revenue:
            rule += f" (revenue: {_money(rev)}, which is not above $1B)"
    elif emp is None:
        tier = "Unknown"
        rule = "Unknown: no employee count found, and revenue does not make the company Enterprise"
    else:
        tier = _tier_by_employees(emp)
        rule = {
            "Mid-market": f"Mid-market: {int(emp):,} employees is between {c.MID_MARKET_EMPLOYEES_MIN} and {c.ENTERPRISE_EMPLOYEES_ABOVE:,}",
            "SMB": f"SMB: {int(emp):,} employees is between {c.SMB_EMPLOYEES_MIN} and {c.MID_MARKET_EMPLOYEES_MIN - 1}",
            "Boutique": f"Boutique: {int(emp):,} employees is fewer than {c.SMB_EMPLOYEES_MIN}",
        }[tier]
        if rev is not None:
            rule += f" (revenue {_money(rev)} is not above $1B)"

    return {
        "tier": tier,
        "rule": rule,
        "basis": {
            "employees": None if emp is None else (int(emp) if float(emp).is_integer() else emp),
            "revenueUsd": None if rev is None else (int(rev) if float(rev).is_integer() else rev),
            "sourceUrls": list(dict.fromkeys(source_urls)),
        },
    }


def _tier_by_employees(emp: float) -> str:
    if emp > c.ENTERPRISE_EMPLOYEES_ABOVE:
        return "Enterprise"
    if emp >= c.MID_MARKET_EMPLOYEES_MIN:
        return "Mid-market"
    if emp >= c.SMB_EMPLOYEES_MIN:
        return "SMB"
    return "Boutique"
