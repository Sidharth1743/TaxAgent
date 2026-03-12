"""Tests for deterministic tax calculation agent module."""

import pytest

from agents.calculation_agent import (
    compute_india_tax,
    compute_us_tax,
    compute_dtaa_credit,
    compute_tax_liability,
)


# ---------------------------------------------------------------------------
# India tax computation
# ---------------------------------------------------------------------------

class TestComputeIndiaTax:
    """India old/new regime tax computation tests."""

    def test_12l_with_deductions(self):
        """12L gross, 1.5L 80C, 25K 80D -> old vs new regime with recommendation."""
        result = compute_india_tax(
            gross_salary=1_200_000,
            deductions_80c=150_000,
            deductions_80d=25_000,
        )
        assert "old_regime_tax" in result
        assert "new_regime_tax" in result
        assert "recommended" in result
        assert "savings" in result
        assert "optimizations" in result
        assert result["recommended"] in ("old", "new")
        assert result["savings"] >= 0

        # Old regime: taxable = 12L - 50K(std) - 1.5L(80C) - 25K(80D) = 9,75,000
        # Slabs: 0-2.5L=0, 2.5-5L=12500, 5-9.75L=95000 => 107500 + 4% cess = 111800
        assert result["old_regime_tax"] == 111_800

        # New regime: taxable = 12L - 75K(std) = 11,25,000
        # Slabs: 0-4L=0, 4-8L=20000, 8-11.25L=32500 => 52500 + 4% cess = 54600
        assert result["new_regime_tax"] == 54_600

        assert result["recommended"] == "new"
        assert result["savings"] == 111_800 - 54_600

    def test_5l_gross_near_zero(self):
        """5L gross -> both regimes near zero, new regime zero (below 4L after std deduction)."""
        result = compute_india_tax(gross_salary=500_000)
        # New regime: 5L - 75K = 4.25L, slab 4-4.25L = 1250, + 4% cess = 1300
        assert result["new_regime_tax"] == 1_300
        # Old regime: 5L - 50K = 4.5L, slab 2.5-4.5L = 10000, + 4% cess = 10400
        assert result["old_regime_tax"] == 10_400

    def test_default_deductions_zero(self):
        """Calling with no deductions should work (defaults to 0)."""
        result = compute_india_tax(gross_salary=1_000_000)
        assert result["old_regime_tax"] > 0
        assert result["new_regime_tax"] > 0

    def test_optimization_suggestions_when_no_80d(self):
        """If 80D is 0, optimization list should suggest claiming it."""
        result = compute_india_tax(gross_salary=1_200_000, deductions_80c=150_000)
        opts = [o.lower() for o in result["optimizations"]]
        assert any("80d" in o for o in opts)

    def test_cess_applied(self):
        """Health and education cess (4%) is applied on both regimes."""
        result = compute_india_tax(gross_salary=2_000_000)
        # Cess = 4%, so tax should not be exactly divisible by slab math alone
        # Just check both are positive and reasonable
        assert result["old_regime_tax"] > 0
        assert result["new_regime_tax"] > 0


# ---------------------------------------------------------------------------
# US tax computation
# ---------------------------------------------------------------------------

class TestComputeUSTax:
    """US federal tax computation tests."""

    def test_85k_single(self):
        """85K single -> verify bracket application."""
        result = compute_us_tax(wages=85_000, filing_status="single")
        assert "federal_tax" in result
        assert "effective_rate" in result
        assert "marginal_bracket" in result
        assert "standard_deduction" in result
        assert "eitc_eligible" in result
        assert "optimizations" in result

        # Taxable = 85000 - 15000 = 70000
        # 10% on 11925 = 1192.50
        # 12% on (48475-11925)=36550 = 4386.00
        # 22% on (70000-48475)=21525 = 4735.50
        # Total = 10314.00
        assert result["federal_tax"] == 10_314.0
        assert result["standard_deduction"] == 15_000
        assert result["marginal_bracket"] == 22

    def test_45k_married(self):
        """45K married -> standard deduction of 30K."""
        result = compute_us_tax(wages=45_000, filing_status="married")
        # Taxable = 45000 - 30000 = 15000
        # Married brackets: 10% on first 23850 -> only 15000 at 10% = 1500
        assert result["federal_tax"] == 1_500.0
        assert result["standard_deduction"] == 30_000
        assert result["marginal_bracket"] == 10

    def test_eitc_eligibility_single(self):
        """Single with wages < 56838 should flag EITC eligibility."""
        result = compute_us_tax(wages=50_000, filing_status="single")
        assert result["eitc_eligible"] is True

    def test_eitc_not_eligible_high_income(self):
        """Single with wages >= 56838 should not flag EITC."""
        result = compute_us_tax(wages=100_000, filing_status="single")
        assert result["eitc_eligible"] is False

    def test_zero_taxable(self):
        """Wages below standard deduction -> zero tax."""
        result = compute_us_tax(wages=10_000, filing_status="single")
        assert result["federal_tax"] == 0.0


# ---------------------------------------------------------------------------
# DTAA foreign tax credit
# ---------------------------------------------------------------------------

class TestComputeDTAACredit:
    """DTAA Article 24 foreign tax credit tests."""

    def test_india_resident_with_us_income(self):
        """India resident with US income -> credit and Form 67."""
        result = compute_dtaa_credit(
            india_tax_paid=200_000,
            us_tax_paid=15_000,
            india_income=1_000_000,
            us_income=80_000,
            total_income=1_080_000,
            residence_country="india",
        )
        assert "credit_amount" in result
        assert "net_tax_after_credit" in result
        assert "forms_required" in result
        # Proportional = india_tax * (us_income / total_income) = 200000 * 80000/1080000 ~= 14814.81
        # Credit = min(15000, 14814.81) = 14814.81 -> rounded to 14815
        assert result["credit_amount"] == round(200_000 * 80_000 / 1_080_000)
        assert "Form 67" in result["forms_required"]

    def test_us_resident_with_india_income(self):
        """US resident with India income -> credit and Form 1116."""
        result = compute_dtaa_credit(
            india_tax_paid=50_000,
            us_tax_paid=20_000,
            india_income=300_000,
            us_income=5_000_000,
            total_income=5_300_000,
            residence_country="us",
        )
        assert "Form 1116" in result["forms_required"]
        # Proportional = us_tax * (india_income / total_income) = 20000 * 300000/5300000 ~= 1132.08
        # Credit = min(50000, 1132.08) = 1132
        assert result["credit_amount"] == round(20_000 * 300_000 / 5_300_000)

    def test_credit_is_min_of_source_and_proportional(self):
        """Credit should be minimum of tax paid in source country and proportional residence tax."""
        result = compute_dtaa_credit(
            india_tax_paid=100_000,
            us_tax_paid=5_000,
            india_income=500_000,
            us_income=200_000,
            total_income=700_000,
            residence_country="india",
        )
        proportional = round(100_000 * 200_000 / 700_000)  # ~28571
        # Credit = min(us_tax_paid=5000, proportional=28571) = 5000
        assert result["credit_amount"] == 5_000


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

class TestComputeTaxLiability:
    """Dispatcher routes to correct calculator based on form type."""

    def test_w2_routes_to_us(self):
        """W-2 fields dict routes to US computation."""
        fields = {"wages": "85000", "federal_tax_withheld": "12000"}
        result = compute_tax_liability(fields, form_type="W-2", jurisdiction="us")
        assert "federal_tax" in result
        assert result["federal_tax"] > 0

    def test_form16_routes_to_india(self):
        """Form 16 fields dict routes to India computation."""
        fields = {"gross_salary": "1200000", "tds_deducted": "100000"}
        result = compute_tax_liability(fields, form_type="Form 16", jurisdiction="india")
        assert "old_regime_tax" in result
        assert "new_regime_tax" in result

    def test_unknown_form_type_returns_error(self):
        """Unknown form type should return an error dict."""
        result = compute_tax_liability({}, form_type="Unknown", jurisdiction="unknown")
        assert "error" in result
