from decimal import Decimal

from pydantic import BaseModel, Field, ConfigDict


class ReceiptItemSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str | None = None
    normalized_name: str
    quantity: Decimal = Decimal("1")
    unit_price: Decimal
    line_total: Decimal
    confidence_score: float = 0.0
    is_uncertain: bool = False


class ReceiptParseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant_name: str | None = None
    receipt_date: str | None = None
    receipt_time: str | None = None
    currency: str = "USD"
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    service_charge: Decimal | None = None
    tips: Decimal | None = None
    total: Decimal | None = None
    items: list[ReceiptItemSchema] = Field(default_factory=list)
    uncertain_fields: list[str] = Field(default_factory=list)
    parsing_notes: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0


class ReceiptVerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    corrected_receipt: ReceiptParseResult
    verification_notes: list[str] = Field(default_factory=list)
    needs_manual_review: bool = False