"""Deterministic tax computation module.

Pure Python -- no LLM calls, no network requests.
Provides India (old/new regime), US federal, and DTAA foreign tax credit calculations.
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# India Tax Computation
# ---------------------------------------------------------------------------

# Old regime slabs (FY 2025-26)
_INDIA_OLD_SLABS: list[tuple[float, float, float]] = [
    (0, 250_000, 0.00),
    (250_000, 500_000, 0.05),
    (500_000, 1_000_000, 0.20),
    (1_000_000, float("inf"), 0.30),
]

# New regime slabs (FY 2025-26, post Budget 2025)
_INDIA_NEW_SLABS: list[tuple[float, float, float]] = [
    (0, 400_000, 0.00),
    (400_000, 800_000, 0.05),
    (800_000, 1_200_000, 0.10),
    (1_200_000, 1_600_000, 0.15),
    (1_600_000, 2_000_000, 0.20),
    (2_000_000, 2_400_000, 0.25),
    (2_400_000, float("inf"), 0.30),
]

_INDIA_OLD_STD_DEDUCTION = 50_000
_INDIA_NEW_STD_DEDUCTION = 75_000
_INDIA_CESS_RATE = 0.04

# Deduction caps
_INDIA_80C_MAX = 150_000
_INDIA_80D_MAX_GENERAL = 25_000
_INDIA_80D_MAX_SENIOR = 50_000
_INDIA_80CCD1B_MAX = 50_000


def _apply_slabs(taxable: float, slabs: list[tuple[float, float, float]]) -> float:
    """Apply progressive slab rates to a taxable amount."""
    tax = 0.0
    for lower, upper, rate in slabs:
        if taxable <= lower:
            break
        bracket_income = min(taxable, upper) - lower
        tax += bracket_income * rate
    return tax


def compute_india_tax(
    gross_salary: int,
    deductions_80c: int = 0,
    deductions_80d: int = 0,
    deductions_80ccd1b: int = 0,
    hra_exemption: int = 0,
    lta_exemption: int = 0,
) -> dict[str, Any]:
    """Compute India income tax under both old and new regimes.

    Returns dict with old_regime_tax, new_regime_tax, recommended, savings, optimizations.
    """
    # --- Old regime ---
    old_taxable = gross_salary - _INDIA_OLD_STD_DEDUCTION
    old_taxable -= min(deductions_80c, _INDIA_80C_MAX)
    old_taxable -= min(deductions_80d, _INDIA_80D_MAX_GENERAL)
    old_taxable -= min(deductions_80ccd1b, _INDIA_80CCD1B_MAX)
    old_taxable -= hra_exemption
    old_taxable -= lta_exemption
    old_taxable = max(old_taxable, 0)

    old_base = _apply_slabs(old_taxable, _INDIA_OLD_SLABS)
    old_cess = old_base * _INDIA_CESS_RATE
    old_total = round(old_base + old_cess)

    # --- New regime ---
    new_taxable = gross_salary - _INDIA_NEW_STD_DEDUCTION
    new_taxable = max(new_taxable, 0)

    new_base = _apply_slabs(new_taxable, _INDIA_NEW_SLABS)
    new_cess = new_base * _INDIA_CESS_RATE
    new_total = round(new_base + new_cess)

    # --- Recommendation ---
    if old_total <= new_total:
        recommended = "old"
        savings = new_total - old_total
    else:
        recommended = "new"
        savings = old_total - new_total

    # --- Optimization suggestions ---
    optimizations: list[str] = []
    if deductions_80c < _INDIA_80C_MAX:
        gap = _INDIA_80C_MAX - deductions_80c
        optimizations.append(
            f"Invest Rs {gap:,} more under Section 80C (PPF/ELSS/NSC) to save up to Rs {round(gap * 0.30 * 1.04):,} in old regime"
        )
    if deductions_80d == 0:
        optimizations.append(
            f"Claim Section 80D health insurance premium to save up to Rs {round(_INDIA_80D_MAX_GENERAL * 0.30 * 1.04):,} in old regime"
        )
    if deductions_80ccd1b == 0:
        optimizations.append(
            f"Invest in NPS under Section 80CCD(1B) to save up to Rs {round(_INDIA_80CCD1B_MAX * 0.30 * 1.04):,} in old regime"
        )

    return {
        "old_regime_tax": old_total,
        "new_regime_tax": new_total,
        "recommended": recommended,
        "savings": savings,
        "optimizations": optimizations,
    }


# ---------------------------------------------------------------------------
# US Tax Computation
# ---------------------------------------------------------------------------

# 2025 federal brackets - single
_US_SINGLE_BRACKETS: list[tuple[float, float, float]] = [
    (0, 11_925, 0.10),
    (11_925, 48_475, 0.12),
    (48_475, 103_350, 0.22),
    (103_350, 197_300, 0.24),
    (197_300, 250_525, 0.32),
    (250_525, 626_350, 0.35),
    (626_350, float("inf"), 0.37),
]

# 2025 federal brackets - married filing jointly
_US_MARRIED_BRACKETS: list[tuple[float, float, float]] = [
    (0, 23_850, 0.10),
    (23_850, 96_950, 0.12),
    (96_950, 206_700, 0.22),
    (206_700, 394_600, 0.24),
    (394_600, 501_050, 0.32),
    (501_050, 751_600, 0.35),
    (751_600, float("inf"), 0.37),
]

_US_STD_DEDUCTION = {"single": 15_000, "married": 30_000}
_US_EITC_LIMIT = {"single": 56_838, "married": 63_398}


def compute_us_tax(
    wages: int,
    filing_status: str = "single",
) -> dict[str, Any]:
    """Compute US federal income tax with standard deduction.

    Returns dict with federal_tax, effective_rate, marginal_bracket,
    standard_deduction, eitc_eligible, optimizations.
    """
    filing_status = filing_status.lower()
    std_deduction = _US_STD_DEDUCTION.get(filing_status, _US_STD_DEDUCTION["single"])
    brackets = _US_SINGLE_BRACKETS if filing_status == "single" else _US_MARRIED_BRACKETS

    taxable = max(wages - std_deduction, 0)
    tax = _apply_slabs(taxable, brackets)

    # Round to nearest dollar (avoid floating point dust)
    tax = round(tax, 2)
    # Truncate to whole dollar as IRS does
    tax = math.floor(tax * 100) / 100
    # For clean output, round to 1 decimal
    tax = round(tax, 1)

    # Determine marginal bracket
    marginal = 0
    for lower, upper, rate in brackets:
        if taxable > lower:
            marginal = int(rate * 100)

    effective_rate = round(tax / wages * 100, 2) if wages > 0 else 0.0

    # Simplified EITC check
    eitc_limit = _US_EITC_LIMIT.get(filing_status, _US_EITC_LIMIT["single"])
    eitc_eligible = wages < eitc_limit

    optimizations: list[str] = []
    if eitc_eligible:
        optimizations.append("You may qualify for the Earned Income Tax Credit (EITC) -- check IRS Form 1040 Schedule EIC")
    if filing_status == "single":
        optimizations.append("Consider maximizing 401(k) contributions ($23,500 limit for 2025) to reduce taxable income")

    return {
        "federal_tax": tax,
        "effective_rate": effective_rate,
        "marginal_bracket": marginal,
        "standard_deduction": std_deduction,
        "eitc_eligible": eitc_eligible,
        "optimizations": optimizations,
    }


# ---------------------------------------------------------------------------
# DTAA Foreign Tax Credit
# ---------------------------------------------------------------------------

def compute_dtaa_credit(
    india_tax_paid: int,
    us_tax_paid: int,
    india_income: int,
    us_income: int,
    total_income: int,
    residence_country: str = "india",
) -> dict[str, Any]:
    """Compute DTAA Article 24 foreign tax credit.

    Credit = min(tax_paid_in_source_country, proportional_tax_in_residence_country)
    Proportional = residence_tax * (foreign_income / total_income)

    Returns dict with credit_amount, net_tax_after_credit, forms_required.
    """
    residence_country = residence_country.lower()

    if residence_country == "india":
        residence_tax = india_tax_paid
        source_tax = us_tax_paid
        foreign_income = us_income
        forms = ["Form 67"]
    else:
        residence_tax = us_tax_paid
        source_tax = india_tax_paid
        foreign_income = india_income
        forms = ["Form 1116"]

    if total_income == 0:
        return {
            "credit_amount": 0,
            "net_tax_after_credit": residence_tax,
            "forms_required": forms,
        }

    proportional = residence_tax * foreign_income / total_income
    credit = min(source_tax, round(proportional))
    net_tax = residence_tax - credit

    return {
        "credit_amount": credit,
        "net_tax_after_credit": net_tax,
        "forms_required": forms,
    }


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def compute_tax_liability(
    fields: dict[str, str],
    form_type: str,
    jurisdiction: str,
) -> dict[str, Any]:
    """Dispatch to the correct tax calculator based on form type and jurisdiction.

    Extracts numeric values from the fields dict (from ExtractedDocument.fields),
    and routes to compute_india_tax or compute_us_tax.
    """
    form_lower = form_type.lower()
    jurisdiction_lower = jurisdiction.lower()

    def _extract_int(key: str) -> int:
        """Extract an integer from fields by key, defaulting to 0."""
        val = fields.get(key, "0")
        try:
            return int(str(val).replace(",", "").replace("$", "").replace("Rs", "").strip())
        except (ValueError, TypeError):
            return 0

    # Route to India
    if "form 16" in form_lower or "form16" in form_lower or jurisdiction_lower == "india":
        return compute_india_tax(
            gross_salary=_extract_int("gross_salary"),
            deductions_80c=_extract_int("deductions_80c"),
            deductions_80d=_extract_int("deductions_80d"),
            deductions_80ccd1b=_extract_int("deductions_80ccd1b"),
            hra_exemption=_extract_int("hra_exemption"),
            lta_exemption=_extract_int("lta_exemption"),
        )

    # Route to US
    if "w-2" in form_lower or "w2" in form_lower or jurisdiction_lower in ("us", "usa"):
        return compute_us_tax(
            wages=_extract_int("wages"),
            filing_status=fields.get("filing_status", "single"),
        )

    return {"error": f"Unsupported form type '{form_type}' with jurisdiction '{jurisdiction}'"}
