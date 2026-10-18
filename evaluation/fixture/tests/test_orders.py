from store.orders import checkout, price_order


def test_order_includes_tax_and_shipping():
    assert price_order(1_000, 2, tax_rate=10) == 2_699


def test_large_order_gets_free_shipping():
    assert price_order(3_000, 2) == 6_000


def test_checkout_reserves_inventory():
    assert checkout(1_000, 2, 5)["remaining"] == 3


def test_checkout_large_coupon_never_negative():
    assert checkout(1_000, 1, 2, coupon_cents=3_000)["total"] == 499
