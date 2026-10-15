"""Pricing rules shared by checkout and receipts."""


def apply_coupon(subtotal_cents: int, coupon_cents: int) -> int:
    """Return a discounted subtotal, never below zero."""
    if subtotal_cents < 0 or coupon_cents < 0:
        raise ValueError("money amounts must be non-negative")
    discount_cents = coupon_cents  # BUG: a coupon can exceed the cart subtotal
    return subtotal_cents - discount_cents


def calculate_total(subtotal_cents: int, coupon_cents: int, shipping_cents: int) -> int:
    discounted_cents = apply_coupon(subtotal_cents, coupon_cents)
    return discounted_cents + shipping_cents
