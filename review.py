"""Turn a diff into a graph-backed impact report with optional LLM tool selection."""
import json
import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import graph
import tools

MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")

SYSTEM = """You are a code review agent with tools backed by FalkorDB.
For each changed function, call impact_of_change to investigate reachable callers
and tests. Then prioritize one changed function and one eligible test for review.
The application validates your choices and renders the report from graph query
results and real test outcomes. Do not claim that a test failed before it runs."""

REASONS = {
    "boundary_case": "The edit may affect a boundary case.",
    "error_handling": "The edit may affect an error path.",
    "behavior_change": "The edit changes behavior worth checking.",
    "changed_test": "The test itself changed in this PR.",
    "unknown": "The graph identifies a useful place to start reviewing.",
}


def short(fid):
    file, _, qual = fid.partition("::")
    return f"{Path(file).stem}:{qual}"


def compute_impacts(changed, hops=4):
    g = tools.get_graph()
    return {f.id: graph.impact(g, f.id, hops) for f in changed}


def selected_test_ids(impacts):
    return sorted({tools.pytest_id(a["id"])
                   for affected in impacts.values() for a in affected if a["is_test"]})


def run_selected_tests(repo, impacts, timeout=180, direct_tests=(), priority_test=None):
    """Run graph-reached and directly changed tests, only when requested."""
    node_ids = sorted(set(selected_test_ids(impacts)) |
                      {tools.pytest_id(fid) for fid in direct_tests})
    if priority_test in node_ids:
        node_ids.remove(priority_test)
        node_ids.insert(0, priority_test)
    if not node_ids:
        return {"node_ids": [], "statuses": {}, "returncode": 0, "output": "No reachable tests."}
    if importlib.util.find_spec("pytest") is None:
        return _run_unittest_targets(repo, node_ids, timeout)
    command = [sys.executable, "-m", "pytest", "-v", "--tb=short", *node_ids]
    try:
        result = subprocess.run(command, cwd=repo, text=True, capture_output=True,
                                timeout=timeout, check=False)
        output = result.stdout + result.stderr
        statuses = {}
        for line in result.stdout.splitlines():
            for node_id in node_ids:
                if line.startswith(node_id + " "):
                    if " PASSED" in line:
                        statuses[node_id] = "passed"
                    elif " FAILED" in line:
                        statuses[node_id] = "failed"
                    elif " ERROR" in line:
                        statuses[node_id] = "error"
        return {"node_ids": node_ids, "statuses": statuses,
                "returncode": result.returncode, "output": output}
    except subprocess.TimeoutExpired:
        return {"node_ids": node_ids, "statuses": {}, "returncode": 124,
                "output": f"Selected tests exceeded the {timeout}s time limit."}


def _run_unittest_targets(repo, node_ids, timeout):
    """Fallback for unittest class methods when pytest is not installed."""
    statuses, output, worst_code = {}, [], 0
    for node_id in node_ids:
        parts = node_id.split("::")
        if len(parts) < 3:
            statuses[node_id] = "unknown"
            output.append(f"Cannot run {node_id} with unittest; install pytest for function tests.")
            worst_code = max(worst_code, 2)
            continue
        module = Path(parts[0]).with_suffix("").as_posix().replace("/", ".")
        target = ".".join([module, *parts[1:]])
        try:
            result = subprocess.run([sys.executable, "-m", "unittest", "-v", target],
                                    cwd=repo, text=True, capture_output=True, timeout=timeout,
                                    check=False)
        except subprocess.TimeoutExpired:
            statuses[node_id] = "error"
            output.append(f"{target}: timed out after {timeout}s")
            worst_code = max(worst_code, 124)
            continue
        combined = result.stdout + result.stderr
        output.append(f"$ python -m unittest -v {target}\n{combined}")
        statuses[node_id] = ("passed" if result.returncode == 0 else
                             "failed" if "FAIL:" in combined else "error")
        worst_code = max(worst_code, result.returncode)
    return {"node_ids": node_ids, "statuses": statuses,
            "returncode": worst_code, "output": "\n".join(output)}


def verification_section(test_run):
    if test_run is None:
        return ""
    statuses = test_run["statuses"]
    lines = ["## Selected test run", "",
             f"Ran {len(test_run['node_ids'])} selected tests "
             f"(exit code {test_run['returncode']}).", ""]
    for node_id in test_run["node_ids"]:
        lines.append(f"- {statuses.get(node_id, 'unknown').upper()}: `{node_id}`")
    lines.extend(["", "```text", test_run["output"][-5000:].rstrip(), "```", ""])
    return "\n".join(lines)


def deterministic_report(changed, impacts, repo=".", test_run=None):
    lines = ["## PR impact report", ""]
    for f in changed:
        aff = impacts[f.id]
        lines.append(f"### `{f.id}` (lines {f.start}-{f.end})")
        if f.is_test:
            note = ("This test changed directly and was included in the selected test run."
                    if test_run is not None else
                    "This test changed directly; use `--run-tests` to verify it.")
            lines += [note, ""]
            continue
        if not aff:
            lines += ["Nothing in the repo calls this function.", ""]
            continue
        tests = [a for a in aff if a["is_test"]]
        direct = [a for a in aff if a["hops"] == 1]
        lines.append(f"- Potentially reaches **{len(aff)}** callers ({len(direct)} direct), including **{len(tests)}** tests")
        far = max(aff, key=lambda a: a["hops"])
        lines.append(f"- Longest chain ({far['hops']} hops): " + " → ".join(f"`{short(n)}`" for n in far["path"]))
        if tests:
            test_ids = ", ".join(f"`{tools.pytest_id(t['id'])}`" for t in tests[:10])
            lines.append(f"- Relevant tests: {test_ids}")
        lines.append("")
    report = "\n".join(lines).rstrip()
    if test_run is not None:
        report += "\n\n" + verification_section(test_run).rstrip()
    return report + "\n"


