"""Unit tests for the Plaid personal_finance_category → name mapping."""

from app.services.categorization import _detailed_suffix, humanize_code


def test_humanize_code():
    assert humanize_code("FOOD_AND_DRINK") == "Food and Drink"
    assert humanize_code("TRANSPORTATION") == "Transportation"
    assert humanize_code("GENERAL_MERCHANDISE") == "General Merchandise"
    assert humanize_code("RENT_AND_UTILITIES") == "Rent and Utilities"
    # a minor word leading the code is still capitalized
    assert humanize_code("THE_WORKS") == "The Works"


def test_detailed_suffix():
    assert (
        _detailed_suffix("FOOD_AND_DRINK", "FOOD_AND_DRINK_COFFEE") == "COFFEE"
    )
    assert (
        _detailed_suffix(
            "TRANSPORTATION", "TRANSPORTATION_TAXIS_AND_RIDE_SHARES"
        )
        == "TAXIS_AND_RIDE_SHARES"
    )
    # detailed same as primary → no child category
    assert _detailed_suffix("INCOME", "INCOME") == ""
