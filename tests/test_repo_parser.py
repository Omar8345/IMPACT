import tempfile
import unittest
from pathlib import Path

from repo_parser import changed_functions, parse_diff, parse_repo


class ParserTests(unittest.TestCase):
    def test_import_alias_chooses_the_right_duplicate_function(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.py").write_text("def charge():\n    pass\n")
            (root / "b.py").write_text("def charge():\n    pass\n")
            (root / "checkout.py").write_text(
                "from a import charge as selected\n"
                "import b as other\n"
                "def first():\n    selected()\n"
                "def second():\n    other.charge()\n"
            )
            _, edges = parse_repo(root)
            self.assertIn(("checkout.py::first", "a.py::charge"), edges)
            self.assertIn(("checkout.py::second", "b.py::charge"), edges)
            self.assertNotIn(("checkout.py::first", "b.py::charge"), edges)

    def test_self_method_and_relative_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "shop"
            package.mkdir()
            (package / "__init__.py").write_text("")
            (package / "price.py").write_text("def total():\n    return 1\n")
            (package / "cart.py").write_text(
                "from .price import total\n"
                "class Cart:\n"
                "    def summary(self):\n        return total()\n"
                "    def checkout(self):\n        return self.summary()\n"
            )
            _, edges = parse_repo(root)
            self.assertIn(("shop/cart.py::Cart.summary", "shop/price.py::total"), edges)
            self.assertIn(("shop/cart.py::Cart.checkout", "shop/cart.py::Cart.summary"), edges)

    def test_package_init_relative_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "shop"
            package.mkdir()
            (package / "price.py").write_text("def total():\n    return 1\n")
            (package / "__init__.py").write_text(
                "from .price import total\n"
                "def quote():\n    return total()\n"
            )
            _, edges = parse_repo(root)
            self.assertIn(("shop/__init__.py::quote", "shop/price.py::total"), edges)

    def test_changed_function_from_git_hunk(self):
        funcs, _ = parse_repo(Path(__file__).parents[1] / "demo_checkout")
        diff = (Path(__file__).parents[1] / "demo_checkout" / "coupon_bug.patch").read_text()
        changed = changed_functions(funcs, parse_diff(diff))
        self.assertEqual([f.id for f in changed], ["shop/pricing.py::apply_coupon"])

    def test_hunk_context_does_not_mark_neighboring_function(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "example.py").write_text(
                "def first():\n    return 2\n\ndef second():\n    return 3\n"
            )
            diff = ("+++ b/example.py\n@@ -1,5 +1,5 @@\n"
                    " def first():\n-    return 1\n+    return 2\n \n"
                    " def second():\n     return 3\n")
            funcs, _ = parse_repo(root)
            changed = changed_functions(funcs, parse_diff(diff))
            self.assertEqual([f.id for f in changed], ["example.py::first"])

    def test_nested_helper_call_is_connected_to_parent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "example.py").write_text(
                "def outer():\n"
                "    def helper():\n"
                "        return 1\n"
                "    return helper()\n"
            )
            _, edges = parse_repo(root)
            self.assertIn(("example.py::outer", "example.py::outer.helper"), edges)


if __name__ == "__main__":
    unittest.main()
