from decimal import Decimal

import pytest

from app.db.models import Participant, Receipt, ReceiptItem, SplitSession
from app.services.split.engine import SplitEngine


def _receipt() -> Receipt:
    return Receipt(
        currency="USD",
        items=[
            ReceiptItem(id=1, normalized_name="Блинчик со сгущеным молоком 100/30", line_total=Decimal("50.00"), quantity=1),
            ReceiptItem(id=2, normalized_name="Чай черный 180 мл", line_total=Decimal("25.00"), quantity=1),
            ReceiptItem(id=3, normalized_name='Блинчик "Фаворит" с ветчиной, сыром, зеленью 100/20/20/5/20', line_total=Decimal("120.00"), quantity=1),
        ],
    )


def _session() -> SplitSession:
    s = SplitSession(id=1, owner_telegram_id=1, receipt_id=1, status="draft")
    s.participants = [Participant(id=1, display_name="me"), Participant(id=2, display_name="Ника"), Participant(id=3, display_name="Аня")]
    s.assignments = []
    return s


def test_ambiguity_question_is_single_and_human():
    engine = SplitEngine()
    question = engine._critical_ambiguity_question("Я плачу за блинчик, Аня за чай, а Ника за блинчик", _receipt())
    assert question == (
        "Critical clarification needed: Уточните, кто платит за 'Блинчик со сгущеным молоком 100/30', "
        "а кто за 'Блинчик \"Фаворит\" с ветчиной, сыром, зеленью 100/20/20/5/20'?"
    )


def test_my_item_correction_resolves_to_current_assignment():
    engine = SplitEngine()
    session = _session()
    receipt = _receipt()
    session.assignments = []
    current = {
        "me": ["Блинчик со сгущеным молоком 100/30"],
        "Ника": ['Блинчик "Фаворит" с ветчиной, сыром, зеленью 100/20/20/5/20'],
        "Аня": ["Чай черный 180 мл"],
    }
    engine._current_assignments = lambda *_args, **_kwargs: current
    result = engine._fallback_parse_actions("Нет, я за Чай, а Аня за блинчик мой", session, receipt)
    assert [a.type for a in result.actions] == ["assign_item", "assign_item"]
    assert result.actions[0].participants == ["me"]
    assert result.actions[0].item_match == "Чай"
    assert result.actions[1].participants == ["Аня"]
    assert result.actions[1].item_match == "Блинчик со сгущеным молоком 100/30"


def test_compact_notes_keeps_one_clarification():
    engine = SplitEngine()
    notes = [
        "Critical clarification needed: Уточните, кто платит за первый блинчик.",
        "Можно прислать исправление обычным текстом, и я пересоберу сплит.",
        "Critical clarification needed: Уточните, кто платит за первый блинчик.",
    ]
    assert engine._compact_notes(notes, ["x"]) == [
        "Critical clarification needed: Уточните, кто платит за первый блинчик."
    ]


def test_no_critical_note_when_everything_is_assigned():
    engine = SplitEngine()
    notes = [
        'Critical clarification needed: Уточните, кто платит за блинчики.',
        'Все позиции распределены. Если что-то не так, просто пришлите исправление.',
    ]
    assert engine._compact_notes(notes, []) == ['Critical clarification needed: Уточните, кто платит за блинчики.']


def test_explicit_assignment_message_is_detected():
    engine = SplitEngine()
    assert engine._is_explicit_assignment_message('Я за чай, а Аня за мой блинчик', ['me', 'Аня', 'Ника']) is True
