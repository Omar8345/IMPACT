from store.inventory import Inventory
from store.pricing import discounted_subtotal
from store.shipping import shipping_fee
from store.tax import tax_cents


def price_order(unit_cents, quantity, coupon_cents=0, percent=0, tax_rate=0):
    subtotal = discounted_subtotal(unit_cents, quantity, coupon_cents, percent)
    return subtotal + tax_cents(subtotal, tax_rate) + shipping_fee(subtotal)


def checkout(unit_cents, quantity, stock, coupon_cents=0, percent=0, tax_rate=0):
    inventory = Inventory(stock)
    remaining = inventory.reserve(quantity)
    total = price_order(unit_cents, quantity, coupon_cents, percent, tax_rate)
    if total < 0:
        raise ValueError("cannot charge a negative amount")
    return {"total": total, "remaining": remaining}
