import pytest

from store.pricing import clamp_coupon, discounted_subtotal, line_total, percentage_discount


def test_line_total_uses_quantity():
    assert line_total(750, 3) == 2_250


def test_line_total_allows_zero_quantity():
    assert line_total(750, 0) == 0


def test_line_total_rejects_negative_quantity():
    with pytest.raises(ValueError):
        line_total(750, -1)


def test_coupon_cannot_exceed_subtotal():
    assert clamp_coupon(2_000, 3_000) == 2_000


def test_negative_coupon_is_ignored():
    assert clamp_coupon(2_000, -500) == 0


def test_percentage_discount_rounds_to_cent():
    assert percentage_discount(1_515, 10) == 152


def test_discounted_subtotal_combines_discounts():
    assert discounted_subtotal(1_000, 2, 100, 10) == 1_700
