from decimal import Decimal

from app.services.receipt.schemas import ReceiptItemSchema, ReceiptParseResult
from app.services.receipt.validator import validate_receipt_math


def test_validate_receipt_math_ok():
    parsed = ReceiptParseResult(
        currency="RUB",
        subtotal=Decimal("300"),
        total=Decimal("330"),
        tax_amount=Decimal("30"),
        items=[
            ReceiptItemSchema(
                normalized_name="Coffee",
                unit_price=Decimal("300"),
                line_total=Decimal("300"),
            )
        ],
    )
    ok, notes = validate_receipt_math(parsed)
    assert ok is True
    assert notes == []
