from decimal import Decimal

from app.services.payments.ton import TonPaymentService


def test_nanotons_conversion():
    service = TonPaymentService()
    assert service.to_nanotons(Decimal("1.5")) == 1500000000
