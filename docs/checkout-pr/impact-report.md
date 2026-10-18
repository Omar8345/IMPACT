# IMPACT review of the Harbor Cart coupon-fix PR

Source: [Omar8345/impact-checkout-demo#1](https://github.com/Omar8345/impact-checkout-demo/pull/1) at commit `2b7aee76b401`. This is a synthetic repository.

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

Ran 3 selected tests (exit code 0).

- PASSED: `tests/test_checkout.py::CheckoutTests::test_checkout_large_coupon`
- PASSED: `tests/test_checkout.py::CheckoutTests::test_checkout_normal_coupon`
- PASSED: `tests/test_receipts.py::ReceiptTests::test_receipt_large_coupon`

```text
============================= test session starts ==============================
platform darwin -- Python 3.14.6, pytest-9.1.1, pluggy-1.7.0 -- python
cachedir: .pytest_cache
rootdir: <temporary PR checkout>
plugins: anyio-4.15.1
collecting ... collected 3 items

tests/test_checkout.py::CheckoutTests::test_checkout_large_coupon PASSED [ 33%]
tests/test_checkout.py::CheckoutTests::test_checkout_normal_coupon PASSED [ 66%]
tests/test_receipts.py::ReceiptTests::test_receipt_large_coupon PASSED   [100%]

============================== 3 passed in 0.08s ===============================
```

## Base vs PR verification

Graph-selected tests from the PR head also ran on the exact base commit when present there; missing tests are inconclusive.
Base: `22d896a95869` · PR head: `2b7aee76b401`.

**2 now passing; 0 new failures.**

| Selected test | Base | PR head | Change |
| --- | --- | --- | --- |
| `tests/test_checkout.py::CheckoutTests::test_checkout_large_coupon` | failed | passed | now passes |
| `tests/test_checkout.py::CheckoutTests::test_checkout_normal_coupon` | passed | passed | passed on both |
| `tests/test_receipts.py::ReceiptTests::test_receipt_large_coupon` | failed | passed | now passes |

<details><summary>Base test output</summary>

```text
============================= test session starts ==============================
platform darwin -- Python 3.14.6, pytest-9.1.1, pluggy-1.7.0 -- python
cachedir: .pytest_cache
rootdir: <temporary PR checkout>
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
========================= 2 failed, 1 passed in 0.09s ==========================
```

</details>

## Agent decision after testing

**Observed:** 2 selected tests did not pass on the base commit and pass on the PR head; no new selected failures were observed.

**Next action:** Review the fix and run any remaining checks before merging.

**FalkorDB path:** `test_checkout:CheckoutTests.test_checkout_large_coupon → checkout:checkout_cart → cart:build_order_summary → pricing:calculate_total → pricing:apply_coupon`

## Engineering context

### `shop/pricing.py::apply_coupon`

**Suggested reviewers:** Maya Chen (Commerce; owns `shop/pricing.py`)
- Chat: **Commerce and Payments agree on the checkout guard** — `company/team-chat.md` (source ID `CHAT-07`)
- Decision: **Coupons never make a cart total negative** — `company/discount-decision.md` (source ID `DEC-14`)
- Ticket: **Large coupon produces a negative charge** — `company/support-ticket.md` (source ID `TICKET-231`)

Ownership and sources come from FalkorDB links. Check the cited files before acting.
