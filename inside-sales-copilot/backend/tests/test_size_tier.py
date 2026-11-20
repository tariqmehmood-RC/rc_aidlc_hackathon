import pytest

from backend.src.services.size_tier import compute_size_tier

B = 1_000_000_000
URLS = ["https://en.wikipedia.org/wiki/X"]


def tier(employees, revenue=None):
    return compute_size_tier(employees, revenue, URLS)["tier"]


@pytest.mark.parametrize("employees,expected", [
    (5001, "Enterprise"),
    (5000, "Mid-market"),
    (4999, "Mid-market"),
    (501, "Mid-market"),
    (500, "Mid-market"),
    (499, "SMB"),
    (51, "SMB"),
    (50, "SMB"),
    (49, "Boutique"),
    (1, "Boutique"),
    (0, "Boutique"),
])
def test_employee_boundaries(employees, expected):
    assert tier(employees) == expected


@pytest.mark.parametrize("revenue,employees,expected", [
    (1.01 * B, 100, "Enterprise"),      # revenue alone makes it Enterprise
    (B + 1, 20, "Enterprise"),
    (B, 100, "SMB"),                    # exactly $1B does not
    (B, 600, "Mid-market"),
    (0.5 * B, 100, "SMB"),
    (5 * B, None, "Enterprise"),        # revenue alone, employees unknown
    (10 * B, 12000, "Enterprise"),
])
def test_revenue_rule(revenue, employees, expected):
    assert tier(employees, revenue) == expected


def test_unknown_when_employees_missing_and_revenue_is_not_enough():
    assert tier(None, None) == "Unknown"
    assert tier(None, 0.9 * B) == "Unknown"
    assert tier(None, B) == "Unknown"


def test_enterprise_wins_when_the_two_numbers_disagree_and_both_are_shown():
    result = compute_size_tier(300, 2 * B, URLS)       # small headcount, big revenue
    assert result["tier"] == "Enterprise"
    assert "300" in result["rule"] and "$2B" in result["rule"] and "SMB" in result["rule"]
    assert result["basis"]["employees"] == 300 and result["basis"]["revenueUsd"] == 2 * B

    result = compute_size_tier(50_000, 100_000_000, URLS)  # big headcount, small revenue
    assert result["tier"] == "Enterprise"
    assert "50,000" in result["rule"] and "$100M" in result["rule"]


def test_rule_text_names_the_numbers_and_the_boundaries():
    assert "5,001" in compute_size_tier(5001, None)["rule"]
    assert "more than 5,000" in compute_size_tier(5001, None)["rule"]
    assert "between 500 and 5,000" in compute_size_tier(1200, None)["rule"]
    assert "between 50 and 499" in compute_size_tier(120, None)["rule"]
    assert "fewer than 50" in compute_size_tier(12, None)["rule"]
    assert "no employee count" in compute_size_tier(None, None)["rule"]


def test_basis_carries_the_numbers_and_source_urls_without_duplicates():
    result = compute_size_tier(1200, None, URLS + URLS + ["https://a.example/"])
    assert result["basis"] == {"employees": 1200, "revenueUsd": None, "sourceUrls": URLS + ["https://a.example/"]}


@pytest.mark.parametrize("bad", ["12000", True, False, float("nan"), float("inf"), -5, [], {}])
def test_invalid_numbers_are_treated_as_unknown(bad):
    assert tier(bad, None) == "Unknown"
    assert tier(None, bad) == "Unknown"


def test_float_employee_counts_work():
    assert tier(5000.0) == "Mid-market"
    assert compute_size_tier(1200.0, None)["basis"]["employees"] == 1200


def test_result_matches_the_research_schema_shape():
    from backend.src.lib import models

    base = {
        "company": {"name": "X", "domain": "x.com", "matchConfidence": "confirmed"}, "retrievedAt": 1,
        "facts": [], "industry": None, "headquarters": None, "employees": None, "revenueUsd": None,
        "sizeTier": compute_size_tier(1200, None, URLS), "news": [], "painPoints": [], "sourcesFetched": [],
    }
    models.validate("research_result", base)
