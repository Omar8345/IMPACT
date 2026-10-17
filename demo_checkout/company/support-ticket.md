# TICKET-231: Large coupon produces a negative charge

Fictional support ticket for the IMPACT demo.

A customer applies a $30 coupon to a $20 cart. The order summary reports -$10,
and checkout rejects the order. The expected total is $0. The report started in
Support, but the likely cause is the discount calculation in Commerce. Payments
owns the checkout guard that surfaced the error.
