# Harbor Cart: PR impact demo

A small, fictional Python checkout service built to demonstrate the PR impact agent.
It also includes a fictional engineering knowledge dataset in `company.json`
and `company/` for the Company Brain demo.
`coupon_bug.patch` records the one-line regression from a working baseline.
The change is intentionally wrong so the agent can trace its effect and the tests
can confirm it. No database, API keys, network, or third-party packages are needed
to run this demo repo's tests.

## Story

Support tickets report that a `$30` coupon on a `$20` cart produces a negative total.
The current commit accidentally removes the cap that kept the discount at or below
the subtotal. The change is in `shop/pricing.py::apply_coupon`, but its callers
span pricing, checkout, receipts, and tests.

## Run the demo

From the parent `files` directory, after connecting the PR impact agent to FalkorDB:

```bash
python main.py index ./demo_checkout
python main.py review ./demo_checkout --diff-file ./demo_checkout/coupon_bug.patch \
  --html ./demo_checkout/impact.html
```

Open `demo_checkout/impact.html` to show the call paths. Then confirm the bug:

```bash
cd demo_checkout
python -m unittest discover -s tests -v
```

The coupon regression test should fail in this checkout. The patch shows the
previous, capped discount calculation and the new buggy line.
The agent's call graph is approximate: it tracks Python function calls by name,
so its report means *potential impact*, not proof that every caller breaks.
