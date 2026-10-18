from store.orders import price_order


def receipt_total(unit_cents, quantity, coupon_cents=0, tax_rate=0):
    return price_order(unit_cents, quantity, coupon_cents, tax_rate=tax_rate)


def format_total(total_cents):
    return f"${total_cents / 100:.2f}"
