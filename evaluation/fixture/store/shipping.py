def shipping_fee(subtotal_cents, free_at_cents=5_000):
    if subtotal_cents >= free_at_cents:
        return 0
    return 499
