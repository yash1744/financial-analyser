"""Unit tests for the Plaid personal_finance_category → name mapping and
the financial classification rules."""

from decimal import Decimal

from app.models.enums import TransactionClassification
from app.services.categorization import _detailed_suffix, classify, humanize_code


def entry(primary: str | None) -> dict:
    if primary is None:
        return {}
    return {
        "personal_finance_category": {
            "primary": primary,
            "detailed": primary,
            "confidence_level": "HIGH",
        }
    }


def test_classify_fixed_primaries():
    out = Decimal("100")
    assert classify(entry("INCOME"), Decimal("-2500")) == TransactionClassification.INCOME
    assert classify(entry("TRANSFER_IN"), Decimal("-200")) == TransactionClassification.TRANSFER
    assert classify(entry("TRANSFER_OUT"), out) == TransactionClassification.TRANSFER
    # credit card payments arrive as LOAN_PAYMENTS → transfer, not expense
    assert classify(entry("LOAN_PAYMENTS"), out) == TransactionClassification.TRANSFER
    assert classify(entry("BANK_FEES"), Decimal("35")) == TransactionClassification.FEE


def test_classify_spending_and_refunds():
    # money out against a spending category → expense
    assert classify(entry("FOOD_AND_DRINK"), Decimal("12.50")) == TransactionClassification.EXPENSE
    assert classify(entry("TRAVEL"), Decimal("500")) == TransactionClassification.EXPENSE
    # money in (negative under Plaid's convention) against a spending
    # category → merchant refund
    refund = classify(entry("GENERAL_MERCHANDISE"), Decimal("-45"))
    assert refund == TransactionClassification.REFUND


def test_classify_without_category_is_unknown():
    assert classify(entry(None), Decimal("10")) == TransactionClassification.UNKNOWN
    no_pfc = classify({"personal_finance_category": None}, Decimal("-10"))
    assert no_pfc == TransactionClassification.UNKNOWN


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
