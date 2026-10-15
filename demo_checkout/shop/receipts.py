"""Receipt preview uses the same pricing rule as checkout."""

from shop.pricing import calculate_total


def receipt_total(subtotal_cents: int, coupon_cents: int) -> int:
    return calculate_total(subtotal_cents, coupon_cents, 0)
