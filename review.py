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


def graph_evidence_section(changed, impacts):
    """Complete graph facts to accompany the model's tool activity."""
    lines = ["## FalkorDB evidence", ""]
    for f in changed:
        affected = impacts[f.id]
        if f.is_test:
            lines.append(f"- `{f.id}` is a changed test; it is selected directly")
            continue
        tests = [a for a in affected if a["is_test"]]
        lines.append(f"- `{f.id}`: {len(affected)} reachable callers; {len(tests)} reachable tests")
        if affected:
            far = max(affected, key=lambda a: a["hops"])
            lines.append("  - Longest path: " + " → ".join(f"`{short(n)}`" for n in far["path"]))
        for test in tests:
            lines.append(f"  - Test: `{tools.pytest_id(test['id'])}`")
    return "\n".join(lines)


def _openrouter_chat(messages, tool_choice="auto", max_tokens=1400):
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("Set OPENROUTER_API_KEY to use --llm, or run without --llm.")
    schemas = [{"type": "function", "function": {"name": item["name"],
                "description": item["description"], "parameters": item["input_schema"]}}
               for item in tools.SCHEMAS]
    body = json.dumps({"model": MODEL, "messages": messages, "tools": schemas,
                       "tool_choice": tool_choice, "temperature": 0.2,
                       "max_tokens": max_tokens}).encode()
    request = Request("https://openrouter.ai/api/v1/chat/completions", data=body,
                      headers={"Authorization": f"Bearer {key}",
                               "Content-Type": "application/json",
                               "X-OpenRouter-Title": "PR Impact Agent"}, method="POST")
    try:
        with urlopen(request, timeout=60) as response:
            payload = json.load(response)
    except HTTPError as exc:
        detail = exc.read(500).decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach OpenRouter: {exc.reason}") from exc
    except ValueError as exc:
        raise RuntimeError("OpenRouter returned invalid JSON.") from exc
    try:
        return payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("OpenRouter returned an incomplete response.") from exc


def llm_decision(changed, diff_text, impacts, direct_tests=()):
    """Let the model inspect graph tools, then validate its review priority."""
    listing = "\n".join(f"- {f.id} (lines {f.start}-{f.end})" for f in changed)
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content":
                 f"Changed functions:\n{listing}\n\nDiff (truncated):\n{diff_text[:12000]}"}]
    queried_changes = {}
    expected = {f.id for f in changed}
    for _ in range(8):
        message = _openrouter_chat(messages)
        messages.append(message)
        calls = message.get("tool_calls") or []
        if not calls:
            break
        for call in calls:
            try:
                name = call["function"]["name"]
                arguments = json.loads(call["function"].get("arguments") or "{}")
                result = tools.TOOLS[name](**arguments)
                out = json.dumps(result)
                if name == "impact_of_change":
                    queried_changes[arguments.get("function_id")] = result["total_affected"]
            except Exception as e:
                out = f"error: {e}"
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": out})
        if expected <= queried_changes.keys():
            break
    missing = expected - queried_changes.keys()
    if missing:
        raise RuntimeError("The model did not query impact for every changed function. "
                           "Try another tool-capable model.")

    directly_changed = {tools.pytest_id(fid) for fid in direct_tests}
    eligible_tests = sorted(set(selected_test_ids(impacts)) | directly_changed)
    focus_choices = [f.id for f in changed if not f.is_test] or [f.id for f in changed]
    candidates = [*sorted(directly_changed),
                  *[tid for tid in eligible_tests if tid not in directly_changed]]
    messages.append({"role": "user", "content":
                     "Choose one review priority from verified graph results. "
                     "Return ONLY a JSON object with keys focus_function, priority_test, reason_code. "
                     "focus_function must be one of: " + json.dumps(focus_choices) + ". "
                     "priority_test must be one of these selected pytest IDs, or null if none: "
                     + json.dumps(candidates[:30]) + ". "
                     "reason_code must be one of: " + json.dumps(list(REASONS)) + ". "
                     "This is a review priority, not a claim that a test failed."})
    response = _openrouter_chat(messages, tool_choice="none", max_tokens=300)
    content = response.get("content")
    if not isinstance(content, str):
        raise RuntimeError("The model did not return a review decision.")
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        decision = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise RuntimeError("The model did not return a valid review decision.") from exc
    if not isinstance(decision, dict):
        raise RuntimeError("The model did not return a valid review decision.")
    focus = decision.get("focus_function")
    priority = decision.get("priority_test")
    reason = decision.get("reason_code")
    valid_priority = priority in candidates[:30] if candidates else priority is None
    if focus not in focus_choices or not valid_priority or reason not in REASONS:
        raise RuntimeError("The model chose a function, test, or reason outside verified options.")
    reachable = {tools.pytest_id(a["id"]): a for a in impacts[focus] if a["is_test"]}
    if priority and priority not in reachable and priority not in directly_changed:
        raise RuntimeError("The model's chosen test has no verified link to its focus function.")

    lines = ["## AI review priority", "",
             "The model queried FalkorDB's `impact_of_change` tool for:", ""]
    for f in changed:
        lines.append(f"- `{f.id}` ({queried_changes[f.id]} reachable callers)")
    lines += ["", f"- **Inspect first:** `{focus}`",
              f"- **Reason to inspect:** {REASONS[reason]}"]
    if priority:
        lines.append(f"- **Run first:** `{priority}`")
        if priority in reachable:
            lines.append("- **Graph path:** " + " → ".join(
                f"`{short(node)}`" for node in reachable[priority]["path"]))
        else:
            lines.append("- **Evidence:** This test changed directly in the PR.")
    else:
        lines.append("- **Run first:** No test was selected by the graph or changed directly.")
    lines += ["", "This is a review priority. Test results appear below only when tests were run."]
    return {"report": "\n".join(lines), "focus_function": focus,
            "priority_test": priority, "reason": REASONS[reason]}


