import unittest

from shop.checkout import checkout_cart


class CheckoutTests(unittest.TestCase):
    def test_checkout_large_coupon(self):
        order = checkout_cart([("Notebook", 2_000, 1)], coupon_cents=3_000)
        self.assertEqual(order["status"], "ready_to_charge")
        self.assertEqual(order["total_cents"], 500)

    def test_checkout_normal_coupon(self):
        order = checkout_cart([("Notebook", 2_000, 1)], coupon_cents=500)
        self.assertEqual(order["total_cents"], 2_000)
