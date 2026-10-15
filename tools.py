"""The agent's tools. Used directly by the agent loop and exposed over MCP."""
import graph

_g = None


def get_graph():
    global _g
    if _g is None:
        _g = graph.connect()
    return _g


def pytest_id(fid):
    file, _, qual = fid.partition("::")
    return f"{file}::{qual.replace('.', '::')}"


def find_function(name: str) -> list:
    """Find function ids in the code graph by exact name or partial id."""
    return graph.find_function(get_graph(), name)


def impact_of_change(function_id: str, max_hops: int = 4) -> dict:
    """List functions and tests that directly or indirectly call this function, with the call path for each."""
    affected = graph.impact(get_graph(), function_id, max_hops)
    return {"function": function_id, "total_affected": len(affected), "affected": affected[:40]}


def tests_to_run(function_id: str, max_hops: int = 4) -> list:
    """pytest ids of the tests that reach this function through calls."""
    affected = graph.impact(get_graph(), function_id, max_hops)
    return [pytest_id(a["id"]) for a in affected if a["is_test"]]


def riskiest_functions(limit: int = 10) -> list:
    """Functions the rest of the codebase depends on most (PageRank). Changes here are riskiest."""
    return graph.risk_rank(get_graph(), limit)


def call_path(from_id: str, to_id: str) -> list:
    """Shortest chain of calls from one function to another, or null if none."""
    return graph.call_path(get_graph(), from_id, to_id)


TOOLS = {f.__name__: f for f in
         (find_function, impact_of_change, tests_to_run, riskiest_functions, call_path)}


def _schema(name, desc, props, required):
    return {"name": name, "description": desc,
            "input_schema": {"type": "object", "properties": props, "required": required}}


_S, _I = {"type": "string"}, {"type": "integer"}
SCHEMAS = [
    _schema("find_function", find_function.__doc__, {"name": _S}, ["name"]),
    _schema("impact_of_change", impact_of_change.__doc__, {"function_id": _S, "max_hops": _I}, ["function_id"]),
    _schema("tests_to_run", tests_to_run.__doc__, {"function_id": _S, "max_hops": _I}, ["function_id"]),
    _schema("riskiest_functions", riskiest_functions.__doc__, {"limit": _I}, []),
    _schema("call_path", call_path.__doc__, {"from_id": _S, "to_id": _S}, ["from_id", "to_id"]),
]
