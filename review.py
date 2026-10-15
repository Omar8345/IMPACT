"""Trace changed functions through the call graph."""
import graph
import tools

def compute_impacts(changed, hops=4):
    g = tools.get_graph()
    return {f.id: graph.impact(g, f.id, hops) for f in changed}

def deterministic_report(changed, impacts):
    lines = ["## PR impact report", ""]
    for f in changed:
        callers = impacts[f.id]
        tests = [a for a in callers if a["is_test"]]
        lines += [f"### `{f.id}`", f"- {len(callers)} reachable callers", f"- {len(tests)} reachable tests", ""]
    return "\n".join(lines)
