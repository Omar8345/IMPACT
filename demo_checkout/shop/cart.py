"""Cart calculations."""

from shop.pricing import calculate_total


def cart_subtotal(items: list[tuple[str, int, int]]) -> int:
    """Items are (name, unit price in cents, quantity)."""
    return sum(price * quantity for _, price, quantity in items)


def build_order_summary(items: list[tuple[str, int, int]], coupon_cents: int) -> dict:
    subtotal_cents = cart_subtotal(items)
    shipping_cents = 500 if subtotal_cents < 5_000 else 0
    total_cents = calculate_total(subtotal_cents, coupon_cents, shipping_cents)
    return {"subtotal_cents": subtotal_cents, "shipping_cents": shipping_cents,
            "total_cents": total_cents}
