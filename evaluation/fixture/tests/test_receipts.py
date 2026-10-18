from store.receipts import format_total, receipt_total


def test_receipt_uses_order_total():
    assert receipt_total(1_000, 2, tax_rate=10) == 2_699


def test_receipt_large_coupon():
    assert receipt_total(1_000, 1, coupon_cents=3_000) == 499


def test_receipt_formats_cents():
    assert format_total(1_299) == "$12.99"
