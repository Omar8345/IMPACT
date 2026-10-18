from store.refunds import refund_amount


def test_refund_is_capped_at_paid_amount():
    assert refund_amount(2_000, 3_000) == 2_000


def test_partial_refund():
    assert refund_amount(2_000, 500) == 500
