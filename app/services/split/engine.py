from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Assignment, Participant, PaymentRequest, Receipt, SplitSession
from app.services.ai.client import OpenAIService
from app.services.payments.ton import TonPaymentService
from app.services.split.schemas import ParsedAction, SplitSummary


class SplitEngine:
    def __init__(self) -> None:
        self.ai = OpenAIService()
        self.payments = TonPaymentService()

    async def create_session(self, db: AsyncSession, receipt_id: int, owner_telegram_id: int) -> SplitSession:
        session = SplitSession(receipt_id=receipt_id, owner_telegram_id=owner_telegram_id, status="draft")
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return session

    async def get_session(self, db: AsyncSession, split_session_id: int) -> SplitSession | None:
        result = await db.execute(
            select(SplitSession)
            .where(SplitSession.id == split_session_id)
            .options(
                selectinload(SplitSession.participants),
                selectinload(SplitSession.assignments),
                selectinload(SplitSession.payment_requests),
            )
        )
        return result.scalar_one_or_none()

    async def add_participants(
        self, db: AsyncSession, split_session_id: int, participant_names: list[str]
    ) -> list[Participant]:
        session = await self.get_session(db, split_session_id)
        if session is None:
            raise ValueError("Split session not found")

        cleaned = [name.strip() for name in participant_names if name.strip()]
        for name in cleaned:
            session.participants.append(Participant(display_name=name))
        await db.commit()
        await db.refresh(session)
        return session.participants

    async def apply_command(
        self, db: AsyncSession, split_session_id: int, receipt: Receipt, command: str
    ) -> tuple[SplitSummary, bool]:
        session = await self.get_session(db, split_session_id)
        if session is None:
            raise ValueError("Split session not found")

        participants = [p.display_name for p in session.participants]
        items = [item.normalized_name for item in receipt.items]
        parsed = await self.ai.parse_split_intent(command, items, participants)

        done = False
        for action in parsed.actions:
            if action.type == "done":
                done = True
                continue
            await self._apply_action(db, session, receipt, action)

        await db.commit()
        summary = await self.build_summary(db, split_session_id, receipt)
        return summary, done

    async def _apply_action(
        self, db: AsyncSession, session: SplitSession, receipt: Receipt, action: ParsedAction
    ) -> None:
        if action.type == "assign_extra_all":
            return

        target_items = [
            item for item in receipt.items if action.item_match and action.item_match.lower() in item.normalized_name.lower()
        ]
        if not target_items:
            return

        participants = [p for p in session.participants if p.display_name in action.participants]
        if not participants and action.type != "exclude_item":
            return

        for item in target_items:
            await db.execute(delete(Assignment).where(Assignment.receipt_item_id == item.id))
            if action.type == "exclude_item":
                continue

            ratios = action.ratios or [Decimal("1") / Decimal(str(len(participants)))] * len(participants)
            ratio_sum = sum(ratios, Decimal("0"))
            if ratio_sum == 0:
                continue

            for participant, raw_ratio in zip(participants, ratios):
                share_ratio = (raw_ratio / ratio_sum).quantize(Decimal("0.000001"))
                amount = (Decimal(item.line_total) * share_ratio).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                db.add(
                    Assignment(
                        split_session_id=session.id,
                        receipt_item_id=item.id,
                        participant_id=participant.id,
                        share_ratio=share_ratio,
                        amount=amount,
                    )
                )

    async def build_summary(self, db: AsyncSession, split_session_id: int, receipt: Receipt) -> SplitSummary:
        session = await self.get_session(db, split_session_id)
        if session is None:
            raise ValueError("Split session not found")

        totals = defaultdict(lambda: Decimal("0.00"))
        assigned_item_ids = set()
        for assignment in session.assignments:
            assigned_item_ids.add(assignment.receipt_item_id)
            participant = next((p for p in session.participants if p.id == assignment.participant_id), None)
            if participant:
                totals[participant.display_name] += Decimal(assignment.amount)

        # Distribute extras proportionally to assigned totals. If no assignments yet, extras stay undistributed.
        extras = sum(
            [
                Decimal(receipt.tax_amount or 0),
                Decimal(receipt.service_charge or 0),
                Decimal(receipt.tips or 0),
            ],
            Decimal("0.00"),
        )
        base_sum = sum(totals.values(), Decimal("0.00"))
        if extras and base_sum > 0:
            names = list(totals.keys())
            distributed = Decimal("0.00")
            for name in names[:-1]:
                extra_share = (extras * (totals[name] / base_sum)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                totals[name] += extra_share
                distributed += extra_share
            if names:
                totals[names[-1]] += extras - distributed

        unassigned_items = [item.normalized_name for item in receipt.items if item.id not in assigned_item_ids]
        summary = SplitSummary(
            currency=receipt.currency,
            totals=[
                {"participant": name, "amount": amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)}
                for name, amount in totals.items()
            ],
            unassigned_items=unassigned_items,
            notes=[],
        )
        if unassigned_items:
            summary.notes.append("Some items are still unassigned.")
        return summary

    async def create_payment_requests(
        self, db: AsyncSession, split_session_id: int, receipt: Receipt
    ) -> list[PaymentRequest]:
        session = await self.get_session(db, split_session_id)
        if session is None:
            raise ValueError("Split session not found")
        summary = await self.build_summary(db, split_session_id, receipt)

        await db.execute(delete(PaymentRequest).where(PaymentRequest.split_session_id == split_session_id))
        requests: list[PaymentRequest] = []
        for total in summary.totals:
            participant = next(p for p in session.participants if p.display_name == total.participant)
            ton_amount = self.payments.convert_fiat_to_ton(total.amount)
            comment = f"Receipt split #{split_session_id} for {participant.display_name}"
            link = self.payments.create_transfer_link(ton_amount=ton_amount, comment=comment)
            req = PaymentRequest(
                split_session_id=split_session_id,
                participant_id=participant.id,
                amount_fiat=total.amount,
                amount_ton=ton_amount,
                payment_link=link,
                comment=comment,
            )
            db.add(req)
            requests.append(req)

        await db.commit()
        refreshed = await db.execute(
            select(PaymentRequest)
            .where(PaymentRequest.split_session_id == split_session_id)
            .options(selectinload(PaymentRequest.participant))
        )
        return list(refreshed.scalars().all())
