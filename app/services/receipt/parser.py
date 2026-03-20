import json
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Receipt, ReceiptItem
from app.services.ai.client import OpenAIService
from app.services.receipt.preprocess import preprocess_receipt_image
from app.services.receipt.schemas import ReceiptParseResult
from app.services.receipt.validator import validate_receipt_math


class ReceiptPipeline:
    def __init__(self) -> None:
        self.ai = OpenAIService()

    async def process(self, db: AsyncSession, telegram_user_id: int, file_id: str, original_path: Path) -> Receipt:
        processed_path = original_path.with_name(f"processed_{original_path.name}")
        preprocess_receipt_image(original_path, processed_path)

        first_pass = await self.ai.parse_receipt(original_path, processed_path)
        verified = await self.ai.verify_receipt(original_path, processed_path, first_pass)
        parsed = verified.corrected_receipt

        ok, math_notes = validate_receipt_math(parsed)
        parse_status = "verified" if ok and not verified.needs_manual_review else "needs_review"
        notes = list(parsed.parsing_notes) + list(verified.verification_notes) + math_notes
        enriched = parsed.model_copy(update={"parsing_notes": notes})

        receipt = Receipt(
            telegram_user_id=telegram_user_id,
            image_file_id=file_id,
            original_image_path=str(original_path),
            processed_image_path=str(processed_path),
            merchant_name=enriched.merchant_name,
            receipt_date=enriched.receipt_date,
            receipt_time=enriched.receipt_time,
            currency=enriched.currency,
            subtotal=enriched.subtotal,
            tax_amount=enriched.tax_amount,
            service_charge=enriched.service_charge,
            tips=enriched.tips,
            total=enriched.total,
            confidence_score=enriched.confidence_score,
            parse_status=parse_status,
            raw_json=enriched.model_dump_json(indent=2),
        )
        for idx, item in enumerate(enriched.items, start=1):
            receipt.items.append(
                ReceiptItem(
                    raw_text=item.raw_text,
                    normalized_name=item.normalized_name,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    line_total=item.line_total,
                    confidence_score=item.confidence_score,
                    is_uncertain=item.is_uncertain,
                    sort_order=idx,
                )
            )

        db.add(receipt)
        await db.commit()
        await db.refresh(receipt)
        return receipt

    @staticmethod
    def pretty_text(parsed: ReceiptParseResult) -> str:
        lines = [f"Receipt: {parsed.merchant_name or 'Unknown merchant'}"]
        for idx, item in enumerate(parsed.items, start=1):
            mark = " ⚠️" if item.is_uncertain else ""
            lines.append(f"{idx}. {item.normalized_name} — {item.line_total} {parsed.currency}{mark}")
        lines.append(f"Total: {parsed.total} {parsed.currency}" if parsed.total is not None else "Total: not found")
        if parsed.parsing_notes:
            lines.append("Notes: " + "; ".join(parsed.parsing_notes[:3]))
        return "\n".join(lines)

    @staticmethod
    def parse_from_db(receipt: Receipt) -> ReceiptParseResult:
        return ReceiptParseResult.model_validate(
            {
                **json.loads(receipt.raw_json or "{}"),
                "items": [
                    {
                        "raw_text": item.raw_text,
                        "normalized_name": item.normalized_name,
                        "quantity": str(item.quantity),
                        "unit_price": str(item.unit_price),
                        "line_total": str(item.line_total),
                        "confidence_score": float(item.confidence_score or 0),
                        "is_uncertain": item.is_uncertain,
                    }
                    for item in sorted(receipt.items, key=lambda x: x.sort_order)
                ],
            }
        )
