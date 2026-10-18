from store.shipping import shipping_fee


def test_shipping_is_free_at_threshold():
    assert shipping_fee(5_000) == 0


def test_shipping_below_threshold():
    assert shipping_fee(4_999) == 499


def test_shipping_above_threshold():
    assert shipping_fee(8_000) == 0
