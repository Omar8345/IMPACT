from store.pricing import clamp_coupon


def refund_amount(paid_cents, requested_cents):
    return clamp_coupon(paid_cents, requested_cents)
