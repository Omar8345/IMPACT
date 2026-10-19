#!/usr/bin/env python3
"""Recheck the committed public PR examples against pinned Git commits."""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import github_pr
import graph
import review
import tools
from repo_parser import changed_functions, parse_diff, parse_repo

EVIDENCE = ROOT / "docs/evaluation/real-world.json"
PATHS = {
    "psf/requests": (
        "tests/test_adapters.py::test_request_url_trims_leading_path_separators",
        "src/requests/adapters.py::HTTPAdapter.request_url",
    ),
    "httpie/cli": (
        "tests/test_sessions.py::test_secure_cookies_on_localhost",
        "httpie/sessions.py::Session.__init__",
    ),
}


def recheck(case):
    owner, name = case["repository"].split("/")
    pr = {
        "owner": owner,
        "repo": name,
        "number": case["pr_number"],
        "base_ref": case["base_ref"],
        "base_sha": case["base_commit"],
        "head_sha": case["analyzed_commit"],
    }
    with github_pr.checkout_pr(pr) as (repo, diff):
        funcs, edges = parse_repo(repo)
        changed = changed_functions(funcs, parse_diff(diff))
        if not changed:
            raise AssertionError(f"{case['repository']}: no changed Python functions found")
        g = graph.connect()
        graph.load(g, funcs, edges)
        tools.set_graph(g)
        impacts = review.compute_impacts(changed)
        selected = set(review.selected_test_ids(impacts))
        selected.update(tools.pytest_id(f.id) for f in changed if f.is_test)
        expected = case["selected_targets"]
        if len(selected) != expected:
            raise AssertionError(
                f"{case['repository']}: selected {len(selected)} test targets; "
                f"committed evidence says {expected}"
            )
        caller, target = PATHS[case["repository"]]
        if caller not in selected:
            raise AssertionError(f"{case['repository']}: missing selected test {caller}")
        path = graph.call_path(g, caller, target)
        if not path or path[0] != caller or path[-1] != target:
            raise AssertionError(f"{case['repository']}: missing FalkorDB call path")
        counts = (case.get("functions_indexed"), case.get("call_edges_indexed"))
        for label, observed, recorded in zip(("functions", "call edges"),
                                             (len(funcs), len(edges)), counts):
            if recorded is not None and observed != recorded:
                raise AssertionError(
                    f"{case['repository']}: {label} changed from {recorded} to {observed}"
                )
        summary = (f"{case['repository']} PR #{case['pr_number']} at "
                   f"{pr['head_sha'][:12]}: {len(funcs)} functions, {len(edges)} "
                   f"call edges, {len(changed)} changed functions, {len(selected)} "
                   f"selected test targets; verified path: {' -> '.join(path)}")
        print(summary)
        if os.getenv("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as output:
                output.write(f"### {case['repository']} PR #{case['pr_number']}\n\n"
                             f"Pinned head: `{pr['head_sha']}`. Graph selection: "
                             f"**{len(selected)} test targets**. Verified path: "
                             f"`{' → '.join(path)}`.\n\n"
                             "Selected tests were not executed in this job.\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", choices=sorted(PATHS))
    args = parser.parse_args()
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    case = next(item for item in evidence["real_prs"]
                if item["repository"] == args.repository)
    recheck(case)


if __name__ == "__main__":
    main()
