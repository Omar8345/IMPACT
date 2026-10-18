"""Build a conservative Python call graph and map Git diffs to functions.

The resolver handles local functions, explicit imports, module aliases, class
constructors, self/cls method calls, and methods on locally constructed objects.
Dynamic dispatch is left unresolved rather than connected by name alone.
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


def _bound_names(target: ast.expr) -> list[str]:
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for item in target.elts for name in _bound_names(item)]
    if isinstance(target, ast.Starred):
        return _bound_names(target.value)
    return []


class _Visitor(ast.NodeVisitor):
    def __init__(self, rel: str):
        self.rel = rel
        self.stack: list[str] = []
        self.callers: list[str] = []
        self.funcs: list[Func] = []
        self.calls: list[tuple[str, list[str], list[str] | None]] = []
        self.local_types: list[dict[str, list[str] | None]] = []
        self.classes: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        self.stack.append(node.name)
        self.classes.append(".".join(self.stack))
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
        self.local_types.append({})
        for child in node.body:
            self.visit(child)
        self.local_types.pop()
        self.callers.pop()
        self.stack.pop()

    visit_FunctionDef = _visit_func
    visit_AsyncFunctionDef = _visit_func

    def visit_Call(self, node: ast.Call):
        if self.callers:
            parts = _call_parts(node.func)
            if parts:
                local_type = (self.local_types[-1].get(parts[0])
                              if len(parts) > 1 else None)
                self.calls.append((self.callers[-1], parts, local_type))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        self.visit(node.value)
        if self.callers:
            constructor = (_call_parts(node.value.func)
                           if isinstance(node.value, ast.Call) else None)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self.local_types[-1][target.id] = constructor
                else:
                    for name in _bound_names(target):
                        self.local_types[-1][name] = None
                    self.visit(target)

    def visit_AnnAssign(self, node: ast.AnnAssign):
        if node.value:
            self.visit(node.value)
        if self.callers and isinstance(node.target, ast.Name):
            self.local_types[-1][node.target.id] = (
                _call_parts(node.value.func) if isinstance(node.value, ast.Call) else None)

    def visit_AugAssign(self, node: ast.AugAssign):
        self.visit(node.value)
        if self.callers and isinstance(node.target, ast.Name):
            self.local_types[-1][node.target.id] = None

    def visit_For(self, node: ast.For | ast.AsyncFor):
        self.visit(node.iter)
        if not self.callers:
            for child in [*node.body, *node.orelse]:
                self.visit(child)
            return
        before = self.local_types[-1].copy()
        for name in _bound_names(node.target):
            self.local_types[-1][name] = None
        for child in [*node.body, *node.orelse]:
            self.visit(child)
        after = self.local_types[-1]
        self.local_types[-1] = {
            name: before.get(name) if before.get(name) == after.get(name) else None
            for name in before.keys() | after.keys()
        }

    visit_AsyncFor = visit_For

    def visit_If(self, node: ast.If):
        self.visit(node.test)
        if not self.callers:
            for child in [*node.body, *node.orelse]:
                self.visit(child)
            return
        before = self.local_types[-1]
        branches = []
        for body in (node.body, node.orelse):
            self.local_types[-1] = before.copy()
            for child in body:
                self.visit(child)
            branches.append(self.local_types[-1])
        left, right = branches
        self.local_types[-1] = {
            name: left.get(name) if left.get(name) == right.get(name) else None
            for name in left.keys() | right.keys()
        }


def _resolve(symbol: str, symbols: dict[str, str]) -> str | None:
    return symbols.get(symbol) or symbols.get(symbol + ".__init__")


def _resolve_call(caller: Func, parts: list[str], module: str,
                  imports: dict[str, str], symbols: dict[str, str],
                  classes: set[str], local_type: list[str] | None = None) -> str | None:
    if local_type and len(parts) == 2:
        root = imports.get(local_type[0], f"{module}.{local_type[0]}")
        class_name = ".".join([root, *local_type[1:]])
        if class_name in classes:
            return _resolve(f"{class_name}.{parts[1]}", symbols)
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
    classes = set()
    for f in funcs:
        module = _module_for_file(f.file)
        symbols[f"{module}.{f.qualname}".strip(".")] = f.id
    for module, visitor, _ in parsed:
        classes.update(f"{module}.{name}".strip(".") for name in visitor.classes)
    by_id = {f.id: f for f in funcs}
    edges = set()
    for module, visitor, imports in parsed:
        for caller_id, parts, local_type in visitor.calls:
            target = _resolve_call(by_id[caller_id], parts, module, imports,
                                   symbols, classes, local_type)
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
