from store.tax import tax_cents


def test_tax_rounds_to_nearest_cent():
    assert tax_cents(999, 8.3) == 83


def test_zero_tax_rate():
    assert tax_cents(2_000, 0) == 0
