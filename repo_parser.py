"""Build a conservative Python call graph and map Git diffs to functions.

The resolver handles local functions, explicit imports, module aliases, class
constructors, and self/cls method calls. Dynamic dispatch is intentionally left
unresolved rather than connected to every function with the same name.
"""

import ast
import re
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {".git", "venv", ".venv", "env", "node_modules", "__pycache__",
             "build", "dist", ".tox", "site-packages"}


@dataclass(frozen=True)
class Func:
    id: str
    name: str
    qualname: str
    file: str
    start: int
    end: int
    is_test: bool


def _module_for_file(rel: str) -> str:
    parts = list(Path(rel).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    if parts and parts[0] == "src":
        parts.pop(0)
    return ".".join(parts)


def _import_target(module: str, node: ast.ImportFrom, package_init: bool) -> str:
    if not node.level:
        return node.module or ""
    package = module if package_init else module.rpartition(".")[0]
    parts = package.split(".") if package else []
    parts = parts[:max(0, len(parts) - node.level + 1)]
    if node.module:
        parts.extend(node.module.split("."))
    return ".".join(parts)


def _imports(tree: ast.Module, module: str, package_init: bool) -> dict[str, str]:
    found = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                found[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            source = _import_target(module, node, package_init)
            for alias in node.names:
                if alias.name != "*":
                    found[alias.asname or alias.name] = f"{source}.{alias.name}".strip(".")
    return found


def _call_parts(expr: ast.expr) -> list[str] | None:
    if isinstance(expr, ast.Name):
        return [expr.id]
    if isinstance(expr, ast.Attribute):
        parent = _call_parts(expr.value)
        return parent + [expr.attr] if parent else None
    return None


class _Visitor(ast.NodeVisitor):
    def __init__(self, rel: str):
        self.rel = rel
        self.stack: list[str] = []
        self.callers: list[str] = []
        self.funcs: list[Func] = []
        self.calls: list[tuple[str, list[str]]] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        self.stack.append(node.name)
        for child in node.body:
            self.visit(child)
        self.stack.pop()

    def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        self.stack.append(node.name)
        qual = ".".join(self.stack)
        fid = f"{self.rel}::{qual}"
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        self.funcs.append(Func(fid, node.name, qual, self.rel, start,
                               node.end_lineno or node.lineno,
                               node.name.startswith("test_")))
        self.callers.append(fid)
        for child in node.body:
            self.visit(child)
        self.callers.pop()
        self.stack.pop()

    visit_FunctionDef = _visit_func
    visit_AsyncFunctionDef = _visit_func

    def visit_Call(self, node: ast.Call):
        if self.callers:
            parts = _call_parts(node.func)
            if parts:
                self.calls.append((self.callers[-1], parts))
        self.generic_visit(node)


def _resolve(symbol: str, symbols: dict[str, str]) -> str | None:
    return symbols.get(symbol) or symbols.get(symbol + ".__init__")


def _resolve_call(caller: Func, parts: list[str], module: str,
                  imports: dict[str, str], symbols: dict[str, str]) -> str | None:
    if parts[0] in {"self", "cls"} and len(parts) == 2 and "." in caller.qualname:
        owner = caller.qualname.rpartition(".")[0]
        return _resolve(f"{module}.{owner}.{parts[1]}", symbols)
    scopes = caller.qualname.split(".")
    for length in range(len(scopes), 0, -1):
        scope = ".".join([module, *scopes[:length]]).strip(".")
        if scope in symbols:
            nested = _resolve(".".join([scope, *parts]), symbols)
            if nested:
                return nested
    if parts[0] in imports:
        return _resolve(".".join([imports[parts[0]], *parts[1:]]), symbols)
    local = _resolve(".".join([module, *parts]), symbols)
    if local:
        return local
    return None


def parse_repo(root: str | Path) -> tuple[list[Func], list[tuple[str, str]]]:
    root = Path(root)
    if not root.is_dir():
        raise ValueError(f"Repository directory does not exist: {root}")
    funcs: list[Func] = []
    parsed = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        if SKIP_DIRS & set(Path(rel).parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=rel)
        except (SyntaxError, UnicodeDecodeError):
            continue
        visitor = _Visitor(rel)
        visitor.visit(tree)
        module = _module_for_file(rel)
        parsed.append((module, visitor, _imports(tree, module, path.name == "__init__.py")))
        funcs.extend(visitor.funcs)
    symbols = {}
    for f in funcs:
        module = _module_for_file(f.file)
        symbols[f"{module}.{f.qualname}".strip(".")] = f.id
    by_id = {f.id: f for f in funcs}
    edges = set()
    for module, visitor, imports in parsed:
        for caller_id, parts in visitor.calls:
            target = _resolve_call(by_id[caller_id], parts, module, imports, symbols)
            if target and target != caller_id:
                edges.add((caller_id, target))
    return funcs, sorted(edges)


def parse_diff(diff_text: str) -> dict[str, list[tuple[int, int]]]:
    """Unified diff -> edited lines on the new (post-change) side."""
    ranges, file, new_line, pending_deletion = {}, None, None, False

    def mark(line):
        if file and file.endswith(".py"):
            ranges.setdefault(file, []).append((max(1, line), max(1, line)))

    def mark_deletion():
        # A deleted-only line has no exact new-side position. Check both sides
        # of the gap so deletions at a function boundary are not missed.
        mark(new_line - 1)
        mark(new_line)

    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            if pending_deletion and new_line is not None:
                mark_deletion()
            file = line[6:] if line.startswith("+++ b/") else None
            new_line, pending_deletion = None, False
        elif line.startswith("@@") and file:
            if pending_deletion and new_line is not None:
                mark_deletion()
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if not match:
                new_line, pending_deletion = None, False
                continue
            new_line, pending_deletion = int(match.group(1)), False
        elif new_line is not None:
            if line.startswith("+"):
                mark(new_line)
                new_line += 1
                pending_deletion = False
            elif line.startswith("-"):
                pending_deletion = True
            elif line.startswith(" "):
                if pending_deletion:
                    mark_deletion()
                    pending_deletion = False
                new_line += 1
            elif not line.startswith("\\"):
                if pending_deletion:
                    mark_deletion()
                new_line, pending_deletion = None, False
    if pending_deletion and new_line is not None:
        mark_deletion()
    return ranges


def changed_functions(funcs: list[Func], ranges: dict[str, list[tuple[int, int]]]) -> list[Func]:
    return [f for f in funcs if any(f.start <= end and start <= f.end
                                  for start, end in ranges.get(f.file, []))]
