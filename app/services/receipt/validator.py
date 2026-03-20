from decimal import Decimal

from app.services.receipt.schemas import ReceiptParseResult


def validate_receipt_math(parsed: ReceiptParseResult) -> tuple[bool, list[str]]:
    notes: list[str] = []
    item_sum = sum((item.line_total for item in parsed.items), Decimal("0"))

    expected_total = item_sum
    for extra in [parsed.tax_amount, parsed.service_charge, parsed.tips]:
        if extra is not None:
            expected_total += extra

    if parsed.subtotal is not None and abs(parsed.subtotal - item_sum) > Decimal("0.05"):
        notes.append(
            f"Subtotal mismatch: parsed subtotal={parsed.subtotal} vs item sum={item_sum}"
        )

    if parsed.total is not None and abs(parsed.total - expected_total) > Decimal("0.05"):
        notes.append(
            f"Total mismatch: parsed total={parsed.total} vs expected={expected_total}"
        )

    if not parsed.items:
        notes.append("No receipt items found")

    return len(notes) == 0, notes
