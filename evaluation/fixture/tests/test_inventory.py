import pytest

from store.inventory import Inventory


def test_exact_stock_is_available():
    inventory = Inventory(3)
    assert inventory.available(3)


def test_reserve_reduces_stock():
    inventory = Inventory(5)
    assert inventory.reserve(2) == 3


def test_reserve_rejects_shortage():
    inventory = Inventory(1)
    with pytest.raises(ValueError):
        inventory.reserve(2)
