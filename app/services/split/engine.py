
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Assignment, Participant, PaymentRequest, Receipt, ReceiptItem, SplitSession
from app.services.ai.client import OpenAIService
from app.services.payments.ton import TonPaymentService
from app.services.split.schemas import ParsedAction, SplitSummary


class SplitEngine:
    CATEGORY_KEYWORDS: dict[str, set[str]] = {
        "drink": {"drink", "drinks", "напиток", "напитки", "кофе", "coffee", "чай", "tea", "вода", "water", "juice", "сок", "морс", "mors", "cola", "soda", "latte", "espresso", "капучино", "americano", "milk", "молоко", "лимонад", "lemonade"},
        "alcohol": {"alcohol", "алкоголь", "beer", "пиво", "wine", "вино", "vodka", "водка", "cocktail", "коктейль", "whiskey", "виски", "rum", "ром", "gin", "джин", "tequila", "текила", "champagne", "шампан"},
        "dessert": {"dessert", "desserts", "десерт", "десерты", "sweet", "сладкое", "cake", "торт", "pie", "пирог", "мусс", "mousse", "icecream", "мороженое", "pancake", "pancakes", "блин", "блины", "блинчики", "мед", "honey", "cream", "сливки", "moulin", "rouge", "мулен"},
        "snack": {"snack", "snacks", "закуска", "закуски", "appetizer", "starter", "fries", "картошка", "salad", "салат", "chips", "чипсы", "nuts", "орехи", "сыр", "cheese", "garnish", "гарнир"},
        "food": {"food", "meal", "еда", "main", "mains", "закуска", "гарнир", "snack", "snacks", "pasta", "паста", "pizza", "пицца", "burger", "бургер", "rice", "рис", "chicken", "курица", "meat", "мясо", "fish", "рыба", "суп", "soup", "лапша", "noodles"},
    }
    CYR_MAP = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya"}

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

    async def add_participants(self, db: AsyncSession, split_session_id: int, participant_names: list[str]) -> list[Participant]:
        session = await self.get_session(db, split_session_id)
        if session is None:
            raise ValueError("Split session not found")
        cleaned = [name.strip() for name in participant_names if name.strip()]
        existing = {self._normalize_text(p.display_name) for p in session.participants}
        for name in cleaned:
            if self._normalize_text(name) not in existing:
                session.participants.append(Participant(display_name=name))
        await db.commit()
        await db.refresh(session)
        return session.participants

    async def apply_command(self, db: AsyncSession, split_session_id: int, receipt: Receipt, command: str) -> tuple[SplitSummary, bool]:
        session = await self.get_session(db, split_session_id)
        if session is None:
            raise ValueError("Split session not found")

        participants = [p.display_name for p in session.participants]
        items = self._build_ai_item_context(receipt.items)
        current_assignments = self._current_assignments(session, receipt)
        parsed = await self.ai.parse_split_intent(command.strip(), items, participants, current_assignments)

        clarification_messages: list[str] = []
        done = False
        for action in parsed.actions:
            if action.type == "done":
                done = True
                continue
            clarification = await self._apply_action(db, session, receipt, action)
            if clarification:
                clarification_messages.append(clarification)

        await db.commit()
        summary = await self.build_summary(db, split_session_id, receipt)

        if clarification_messages:
            summary.notes.extend(clarification_messages)
        elif parsed.needs_clarification and parsed.clarification_question:
            summary.notes.append("Critical clarification needed: " + parsed.clarification_question)
        elif done and summary.unassigned_items:
            summary.notes.append("Critical clarification needed: who should pay for the remaining items?")

        return summary, done

    def _normalize_text(self, text: str) -> str:
        text = (text or "").lower().replace("ё", "е")
        transliterated = "".join(self.CYR_MAP.get(ch, ch) for ch in text)
        cleaned = unicodedata.normalize("NFKD", transliterated)
        cleaned = "".join(ch for ch in cleaned if not unicodedata.combining(ch))
        cleaned = re.sub(r"[^a-z0-9а-я\s]+", " ", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    def _tokenize(self, text: str) -> list[str]:
        return [token for token in self._normalize_text(text).split() if token]

    def _category_for_item(self, item: ReceiptItem) -> str | None:
        tokens = set(self._tokenize(item.normalized_name) + self._tokenize(item.raw_text or ""))
        best_category = None
        best_score = 0
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            score = len(tokens & {self._normalize_text(k) for k in keywords})
            if score > best_score:
                best_category = category
                best_score = score
        return best_category

    def _item_aliases(self, item: ReceiptItem) -> set[str]:
        aliases = set(self._tokenize(item.normalized_name)) | set(self._tokenize(item.raw_text or ""))
        category = self._category_for_item(item)
        if category:
            aliases |= {self._normalize_text(k) for k in self.CATEGORY_KEYWORDS.get(category, set())}
            aliases.add(category)
        joined = self._normalize_text(item.normalized_name)
        if joined:
            aliases.add(joined)
        return {a for a in aliases if a}

    def _build_ai_item_context(self, items: list[ReceiptItem]) -> list[str]:
        context = []
        for item in items:
            category = self._category_for_item(item) or "other"
            aliases = ", ".join(sorted(self._item_aliases(item))[:16])
            base = self._base_item_label(item)
            context.append(f"{item.normalized_name} | base={base} | category={category} | aliases={aliases}")
        return context

    def _current_assignments(self, session: SplitSession, receipt: Receipt) -> dict[str, list[str]]:
        result: dict[str, list[str]] = defaultdict(list)
        pmap = {p.id: p.display_name for p in session.participants}
        imap = {i.id: i.normalized_name for i in receipt.items}
        for a in session.assignments:
            if a.participant_id in pmap and a.receipt_item_id in imap:
                result[pmap[a.participant_id]].append(imap[a.receipt_item_id])
        return dict(result)

    def _base_item_label(self, item: ReceiptItem) -> str:
        tokens = self._tokenize(item.normalized_name)
        return tokens[0] if tokens else self._normalize_text(item.normalized_name)

    def _is_ambiguous_match(self, query: str, target_items: list[ReceiptItem]) -> bool:
        q_tokens = self._tokenize(query)
        if len(target_items) <= 1:
            return False
        if len(q_tokens) > 2:
            return False
        bases = {self._base_item_label(item) for item in target_items}
        if len(bases) != 1:
            return False
        distinctive = []
        for item in target_items:
            toks = set(self._tokenize(item.normalized_name))
            toks.discard(next(iter(bases)))
            distinctive.append(toks)
        if not distinctive:
            return False
        query_set = set(q_tokens)
        if any(query_set & d for d in distinctive):
            return False
        return True

    def _clarification_for_items(self, query: str, target_items: list[ReceiptItem]) -> str:
        names = "; ".join(item.normalized_name for item in target_items)
        return f"Critical clarification needed: you mentioned '{query}', but several different items match it. Please specify who pays for each of these: {names}."

    async def _apply_action(self, db: AsyncSession, session: SplitSession, receipt: Receipt, action: ParsedAction) -> str | None:
        target_items: list[ReceiptItem] = []
        if action.type in {"assign_by_category", "split_by_category"} and action.category:
            target_items = [i for i in receipt.items if self._category_for_item(i) == action.category]
        elif action.type == "assign_remaining":
            assigned = {a.receipt_item_id for a in session.assignments}
            target_items = [i for i in receipt.items if i.id not in assigned]
        elif action.item_match:
            query = self._normalize_text(action.item_match)
            for item in receipt.items:
                hay = self._normalize_text(item.normalized_name)
                if query and (query in hay or hay in query):
                    target_items.append(item)
            if not target_items:
                for item in receipt.items:
                    aliases = self._item_aliases(item)
                    if query in aliases or any(tok in aliases for tok in self._tokenize(query)):
                        target_items.append(item)
            if self._is_ambiguous_match(query, target_items):
                return self._clarification_for_items(action.item_match, target_items)
        if not target_items:
            return None

        participants = [p for p in session.participants if p.display_name in action.participants]
        if action.type != "exclude_item" and not participants:
            return None

        for item in target_items:
            await db.execute(delete(Assignment).where(Assignment.receipt_item_id == item.id))
            if action.type == "exclude_item":
                continue
            if action.type in {"assign_item", "assign_by_category", "assign_remaining"} and len(participants) >= 1 and not action.ratios:
                ratios = [Decimal("1")] + [Decimal("0")] * (len(participants) - 1)
            else:
                ratios = action.ratios or [Decimal("1") / Decimal(str(len(participants)))] * len(participants)
            ratio_sum = sum(ratios, Decimal("0"))
            if ratio_sum == 0:
                continue
            distributed = Decimal("0.00")
            for idx, (participant, raw_ratio) in enumerate(zip(participants, ratios)):
                share_ratio = (raw_ratio / ratio_sum).quantize(Decimal("0.000001"))
                amount = (Decimal(item.line_total) * share_ratio).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                distributed += amount
                db.add(Assignment(split_session_id=session.id, receipt_item_id=item.id, participant_id=participant.id, share_ratio=share_ratio, amount=amount))
            drift = Decimal(item.line_total).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) - distributed
            if drift != 0 and participants:
                result = await db.execute(select(Assignment).where(Assignment.receipt_item_id == item.id, Assignment.participant_id == participants[-1].id))
                last_assignment = result.scalar_one_or_none()
                if last_assignment is not None:
                    last_assignment.amount = Decimal(last_assignment.amount) + drift
        return None

    async def build_summary(self, db: AsyncSession, split_session_id: int, receipt: Receipt) -> SplitSummary:
        session = await self.get_session(db, split_session_id)
        if session is None:
            raise ValueError("Split session not found")
        totals = defaultdict(lambda: Decimal("0.00"))
        participant_items: dict[str, list[str]] = defaultdict(list)
        assigned_item_ids = set()
        for assignment in session.assignments:
            assigned_item_ids.add(assignment.receipt_item_id)
            participant = next((p for p in session.participants if p.id == assignment.participant_id), None)
            item = next((i for i in receipt.items if i.id == assignment.receipt_item_id), None)
            if participant:
                totals[participant.display_name] += Decimal(assignment.amount)
                if item:
                    participant_items[participant.display_name].append(item.normalized_name)
        extras = sum([Decimal(receipt.tax_amount or 0), Decimal(receipt.service_charge or 0), Decimal(receipt.tips or 0)], Decimal("0.00"))
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
            totals=[{"participant": name, "amount": amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "items": participant_items.get(name, [])} for name, amount in totals.items()],
            unassigned_items=unassigned_items,
            notes=[],
        )
        if unassigned_items:
            summary.notes.append("Some items are still unassigned. If your last instruction should have covered them, just correct me in plain language.")
        else:
            summary.notes.append("Everything is assigned. Type done to finalize or send corrections.")
        return summary

    async def create_payment_requests(self, db: AsyncSession, split_session_id: int, receipt: Receipt) -> list[PaymentRequest]:
        session = await self.get_session(db, split_session_id)
        if session is None:
            raise ValueError("Split session not found")
        summary = await self.build_summary(db, split_session_id, receipt)
        if summary.unassigned_items:
            return []
        await db.execute(delete(PaymentRequest).where(PaymentRequest.split_session_id == split_session_id))
        for total in summary.totals:
            participant = next(p for p in session.participants if p.display_name == total.participant)
            ton_amount = self.payments.convert_fiat_to_ton(total.amount)
            comment = f"Receipt split #{split_session_id} for {participant.display_name}"
            link = self.payments.create_transfer_link(ton_amount=ton_amount, comment=comment)
            db.add(PaymentRequest(split_session_id=split_session_id, participant_id=participant.id, amount_fiat=total.amount, amount_ton=ton_amount, payment_link=link, comment=comment))
        await db.commit()
        refreshed = await db.execute(select(PaymentRequest).where(PaymentRequest.split_session_id == split_session_id).options(selectinload(PaymentRequest.participant)))
        return list(refreshed.scalars().all())
