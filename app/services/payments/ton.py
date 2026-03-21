from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import quote

from app.core.config import get_settings


class TonPaymentService:
    """
    TON MVP integration via a web URL that opens in the browser,
    instead of ton:// deep links.
    """

    APPROX_TON_RATE = Decimal("300")  # demo-only conversion.

    def __init__(self) -> None:
        self.receiver = get_settings().ton_receiver_address

    def convert_fiat_to_ton(self, amount: Decimal) -> Decimal:
        return (amount / self.APPROX_TON_RATE).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def to_nanotons(ton_amount: Decimal) -> int:
        return int((ton_amount * Decimal("1000000000")).to_integral_value(rounding=ROUND_HALF_UP))

    def create_transfer_link(self, ton_amount: Decimal, comment: str) -> str:
        nanotons = self.to_nanotons(ton_amount)
        return f"https://app.tonkeeper.com/transfer/{self.receiver}?amount={nanotons}&text={quote(comment)}"
