# Synthetic coupon regression — IMPACT agent review

## AI review priority

The model queried FalkorDB's `impact_of_change` tool for:

- `shop/pricing.py::apply_coupon` (7 reachable callers)

- **Inspect first:** `shop/pricing.py::apply_coupon`
- **Reason to inspect:** The edit may affect a boundary case.
- **Run first:** `tests/test_checkout.py::CheckoutTests::test_checkout_large_coupon`
- **Graph path:** `test_checkout:CheckoutTests.test_checkout_large_coupon` → `checkout:checkout_cart` → `cart:build_order_summary` → `pricing:calculate_total` → `pricing:apply_coupon`

This is a review priority. Test results appear below only when tests were run.

## FalkorDB evidence

- `shop/pricing.py::apply_coupon`: 7 reachable callers; 3 reachable tests
  - Longest path: `test_checkout:CheckoutTests.test_checkout_large_coupon` → `checkout:checkout_cart` → `cart:build_order_summary` → `pricing:calculate_total` → `pricing:apply_coupon`
  - Test: `tests/test_receipts.py::ReceiptTests::test_receipt_large_coupon`
  - Test: `tests/test_checkout.py::CheckoutTests::test_checkout_large_coupon`
  - Test: `tests/test_checkout.py::CheckoutTests::test_checkout_normal_coupon`

## Selected test run

Ran 3 selected tests (exit code 1).

- FAILED: `tests/test_checkout.py::CheckoutTests::test_checkout_large_coupon`
- PASSED: `tests/test_checkout.py::CheckoutTests::test_checkout_normal_coupon`
- FAILED: `tests/test_receipts.py::ReceiptTests::test_receipt_large_coupon`

```text
============================= test session starts ==============================
platform darwin -- Python 3.14.6, pytest-9.1.1, pluggy-1.7.0 -- <IMPACT virtualenv>/bin/python
cachedir: .pytest_cache
rootdir: <synthetic demo checkout>
plugins: anyio-4.15.1
collecting ... collected 3 items

tests/test_checkout.py::CheckoutTests::test_checkout_large_coupon FAILED [ 33%]
tests/test_checkout.py::CheckoutTests::test_checkout_normal_coupon PASSED [ 66%]
tests/test_receipts.py::ReceiptTests::test_receipt_large_coupon FAILED   [100%]

=================================== FAILURES ===================================
___________________ CheckoutTests.test_checkout_large_coupon ___________________
tests/test_checkout.py:8: in test_checkout_large_coupon
    order = checkout_cart([("Notebook", 2_000, 1)], coupon_cents=3_000)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
shop/checkout.py:9: in checkout_cart
    raise ValueError("cannot charge a negative amount")
E   ValueError: cannot charge a negative amount
____________________ ReceiptTests.test_receipt_large_coupon ____________________
tests/test_receipts.py:8: in test_receipt_large_coupon
    self.assertEqual(receipt_total(2_000, 3_000), 0)
E   AssertionError: -1000 != 0
=========================== short test summary info ============================
FAILED tests/test_checkout.py::CheckoutTests::test_checkout_large_coupon - Va...
FAILED tests/test_receipts.py::ReceiptTests::test_receipt_large_coupon - Asse...
========================= 2 failed, 1 passed in 0.11s ==========================
```

## Agent decision after testing

**Observed:** Selected tests failed.

**Next action:** Review the candidate fix, then rerun the selected tests.

**FalkorDB path:** `test_checkout:CheckoutTests.test_checkout_large_coupon → checkout:checkout_cart → cart:build_order_summary → pricing:calculate_total → pricing:apply_coupon`

**Candidate fix (unverified):** Update shop/pricing.py::apply_coupon to cap the discount at the subtotal: restore `discount_cents = min(subtotal_cents, coupon_cents)` so an oversized coupon returns zero rather than a negative amount.
