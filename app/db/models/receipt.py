from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[int] = mapped_column(index=True)
    image_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_image_path: Mapped[str] = mapped_column(String(500))
    processed_image_path: Mapped[str] = mapped_column(String(500))
    merchant_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    receipt_date: Mapped[str | None] = mapped_column(String(30), nullable=True)
    receipt_time: Mapped[str | None] = mapped_column(String(30), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    subtotal: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    tax_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    service_charge: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    tips: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(50), default="parsed")
    raw_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    items: Mapped[list["ReceiptItem"]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan", lazy="selectin"
    )


class ReceiptItem(Base):
    __tablename__ = "receipt_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"), index=True)
    raw_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 3), default=Decimal("1.000"))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    line_total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    confidence_score: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    is_uncertain: Mapped[bool] = mapped_column(default=False)
    sort_order: Mapped[int] = mapped_column(default=0)

    receipt: Mapped[Receipt] = relationship(back_populates="items")
