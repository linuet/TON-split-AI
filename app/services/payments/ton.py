from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import quote

from app.core.config import get_settings


class TonPaymentService:
    """
    Simple TON MVP integration via transfer deep links.
    For hackathon demos this is enough to show a real payment handoff.
    """

    APPROX_TON_RATE = Decimal("300")  # 1 TON ~= 300 fiat units for demo-only conversion.

    def __init__(self) -> None:
        self.receiver = get_settings().ton_receiver_address

    def convert_fiat_to_ton(self, amount: Decimal) -> Decimal:
        return (amount / self.APPROX_TON_RATE).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def to_nanotons(ton_amount: Decimal) -> int:
        return int((ton_amount * Decimal("1000000000")).to_integral_value(rounding=ROUND_HALF_UP))

    def create_transfer_link(self, ton_amount: Decimal, comment: str) -> str:
        nanotons = self.to_nanotons(ton_amount)
        return f"ton://transfer/{self.receiver}?amount={nanotons}&text={quote(comment)}"
