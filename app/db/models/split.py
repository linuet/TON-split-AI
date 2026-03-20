from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class SplitSession(Base):
    __tablename__ = "split_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id", ondelete="CASCADE"), index=True)
    owner_telegram_id: Mapped[int] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(50), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    participants: Mapped[list["Participant"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="selectin"
    )
    assignments: Mapped[list["Assignment"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="selectin"
    )
    payment_requests: Mapped[list["PaymentRequest"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", lazy="selectin"
    )


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    split_session_id: Mapped[int] = mapped_column(ForeignKey("split_sessions.id", ondelete="CASCADE"), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    telegram_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped[SplitSession] = relationship(back_populates="participants")
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="participant", lazy="selectin")
    payment_requests: Mapped[list["PaymentRequest"]] = relationship(back_populates="participant", lazy="selectin")


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    split_session_id: Mapped[int] = mapped_column(ForeignKey("split_sessions.id", ondelete="CASCADE"), index=True)
    receipt_item_id: Mapped[int] = mapped_column(ForeignKey("receipt_items.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    share_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 6))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))

    session: Mapped[SplitSession] = relationship(back_populates="assignments")
    participant: Mapped[Participant] = relationship(back_populates="assignments")


class PaymentRequest(Base):
    __tablename__ = "payment_requests"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    split_session_id: Mapped[int] = mapped_column(ForeignKey("split_sessions.id", ondelete="CASCADE"), index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id", ondelete="CASCADE"), index=True)
    amount_fiat: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    amount_ton: Mapped[Decimal] = mapped_column(Numeric(18, 9))
    status: Mapped[str] = mapped_column(String(50), default="created")
    payment_link: Mapped[str] = mapped_column(String(1000))
    comment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    session: Mapped[SplitSession] = relationship(back_populates="payment_requests")
    participant: Mapped[Participant] = relationship(back_populates="payment_requests")
