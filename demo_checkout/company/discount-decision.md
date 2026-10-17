# DEC-14: Coupons never make a cart total negative

Fictional engineering decision for the IMPACT demo.

The Commerce team owns the discount calculation. A coupon can reduce the subtotal
to zero, but it must never create a negative balance. `apply_coupon` must cap the
discount at the subtotal. Payments should not be asked to correct negative totals
after the fact.
