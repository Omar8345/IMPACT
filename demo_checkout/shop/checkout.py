"""Checkout orchestration."""

from shop.cart import build_order_summary


def checkout_cart(items: list[tuple[str, int, int]], coupon_cents: int) -> dict:
    summary = build_order_summary(items, coupon_cents)
    if summary["total_cents"] < 0:
        raise ValueError("cannot charge a negative amount")
    return {"status": "ready_to_charge", **summary}
