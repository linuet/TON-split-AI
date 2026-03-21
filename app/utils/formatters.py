from app.db.models import PaymentRequest, Receipt
from app.services.receipt.parser import ReceiptPipeline
from app.services.split.schemas import SplitSummary


def format_receipt(receipt: Receipt) -> str:
    parsed = ReceiptPipeline.parse_from_db(receipt)

    lines = [f"🧾 <b>{parsed.merchant_name or 'Receipt parsed'}</b>"]

    for idx, item in enumerate(parsed.items, start=1):
        mark = " ⚠️" if item.is_uncertain else ""
        lines.append(
            f"{idx}. {item.normalized_name} — <b>{item.line_total}</b> {parsed.currency}{mark}"
        )

    if parsed.total is not None:
        lines.append(f"\n💳 Total: <b>{parsed.total}</b> {parsed.currency}")

    if parsed.parsing_notes:
        lines.append("\nℹ️ " + "; ".join(parsed.parsing_notes[:3]))

    return "\n".join(lines)


def format_summary(summary: SplitSummary) -> str:
    lines = ["📊 <b>Split summary</b>"]

    for total in summary.totals:
        lines.append(f"• {total.participant}: <b>{total.amount}</b> {summary.currency}")

        if total.items:
            preview = ", ".join(total.items[:4])
            if len(total.items) > 4:
                preview += ", ..."
            lines.append(f"  ↳ {preview}")

    if summary.unassigned_items:
        lines.append("\n⚠️ Unassigned items: " + ", ".join(summary.unassigned_items))

    if summary.notes:
        lines.append("ℹ️ " + "; ".join(summary.notes))

    lines.append("\n✍️ If anything is wrong, send a correction in plain language.")

    return "\n".join(lines)


def format_payment_requests(requests: list[PaymentRequest]) -> str:
    lines = ["💎 <b>TON payment links</b>"]

    for req in requests:
        participant_name = (
            req.participant.display_name
            if req.participant
            else f"Participant #{req.participant_id}"
        )

        lines.append(
            f"• {participant_name}: <b>{req.amount_ton}</b> TON "
            f"for <b>{req.amount_fiat}</b> fiat\n"
            f'  <a href="{req.payment_link}">Open TON payment page</a>'
        )

    return "\n".join(lines)