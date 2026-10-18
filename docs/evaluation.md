# IMPACT test-selection evaluation

This evaluation applies each mutation independently, runs the complete test suite to establish ground truth, and then measures which failure-revealing tests each selection method would have chosen.

| Method | Failure recall | Test reduction | Failure yield | Selected runs |
| --- | ---: | ---: | ---: | ---: |
| Filename match | 58.6% | 80.0% | 23.6% | 72 |
| Direct callers | 55.2% | 91.4% | 51.6% | 31 |
| IMPACT (FalkorDB) | 100.0% | 69.2% | 26.1% | 111 |
| Full suite | 100.0% | 0.0% | 8.1% | 360 |

The fixture contains **24 tests** and **15 controlled mutations**. Failure recall measures how many tests that failed in the full run were selected. Test reduction measures how many test executions were avoided. Failure yield is the share of selected tests that exposed the injected defect; passing selected tests can still be relevant to the changed behavior.

## Per-mutation results

| Mutation | Full-suite failures | Filename recall | Direct recall | IMPACT recall | IMPACT selected |
| --- | ---: | ---: | ---: | ---: | ---: |
| `coupon_cap_removed` | 4 | 25% | 25% | 100% | 11/24 |
| `negative_coupon_accepted` | 1 | 100% | 100% | 100% | 11/24 |
| `quantity_ignored` | 6 | 50% | 33% | 100% | 10/24 |
| `zero_quantity_charged` | 1 | 100% | 100% | 100% | 10/24 |
| `negative_quantity_allowed` | 1 | 100% | 100% | 100% | 10/24 |
| `percentage_rounding_changed` | 1 | 100% | 100% | 100% | 8/24 |
| `combined_discount_dropped` | 1 | 100% | 100% | 100% | 7/24 |
| `tax_rounding_changed` | 1 | 100% | 100% | 100% | 8/24 |
| `shipping_threshold_exclusive` | 1 | 100% | 100% | 100% | 9/24 |
| `shipping_fee_increased` | 5 | 20% | 20% | 100% | 9/24 |
| `exact_stock_rejected` | 1 | 100% | 100% | 100% | 5/24 |
| `reserve_does_not_decrement` | 2 | 50% | 50% | 100% | 4/24 |
| `tax_omitted_from_order` | 2 | 50% | 50% | 100% | 6/24 |
| `receipt_decimal_shift` | 1 | 100% | 100% | 100% | 1/24 |
| `refund_cap_removed` | 1 | 100% | 100% | 100% | 2/24 |

## Reproduce it

Start FalkorDB, install the project requirements, and run:

```bash
python evaluation/run.py
```

The command rewrites `evaluation/results.json`, the published HTML summary, and this report. The fixture uses synthetic data and the benchmark does not call an LLM.

## Scope

This is a controlled benchmark of static Python call-graph test selection. It does not measure every Python pattern or claim production-wide accuracy. Dynamic dispatch, reflection, native extensions, and runtime imports can hide relationships from static analysis. The committed scenarios, fixture, mutations, raw results, and scoring code are included so the numbers can be inspected and rerun.
