import unittest

from shop.receipts import receipt_total


class ReceiptTests(unittest.TestCase):
    def test_receipt_large_coupon(self):
        self.assertEqual(receipt_total(2_000, 3_000), 0)
