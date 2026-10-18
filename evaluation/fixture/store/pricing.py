def line_total(unit_cents, quantity):
    if quantity < 0:
        raise ValueError("quantity cannot be negative")
    return unit_cents * quantity


def clamp_coupon(subtotal_cents, coupon_cents):
    return max(0, min(subtotal_cents, coupon_cents))


def percentage_discount(subtotal_cents, percent):
    return round(subtotal_cents * percent / 100)


def discounted_subtotal(unit_cents, quantity, coupon_cents=0, percent=0):
    subtotal = line_total(unit_cents, quantity)
    discount = clamp_coupon(subtotal, coupon_cents + percentage_discount(subtotal, percent))
    return subtotal - discount
