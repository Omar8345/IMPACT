#!/usr/bin/env python3
"""Recheck the committed public PR examples against pinned Git commits."""

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree

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


def run_selected_tests(repo, case, selected):
    extras = "[test]" if case["repository"] == "httpie/cli" else ""
    packages = [f"{repo}{extras}", "pytest>=7,<8", "pytest-httpbin==2.0.0"]
    if case["repository"] == "httpie/cli":
        packages.append("urllib3>=1.26,<2")
    else:
        packages.append("pytest-mock")
    install = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
         "--no-input", "--editable", packages[0], *packages[1:]],
        text=True, capture_output=True, timeout=300, check=False,
    )
    if install.returncode:
        raise RuntimeError(f"Test dependency installation failed:\n{install.stdout[-3000:]}\n"
                           f"{install.stderr[-3000:]}")

    with tempfile.TemporaryDirectory(prefix="impact-pr-test-") as temporary:
        xml = Path(temporary) / "results.xml"
        command = [sys.executable, "-m", "pytest", "-q", "--tb=short",
                   "-o", "addopts=", f"--junitxml={xml}"]
        if case["repository"] == "httpie/cli":
            command.extend(["-p", "evaluation.offline_httpie"])
        command.extend(sorted(selected))
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join((str(ROOT), str(repo), str(repo / "src")))
        result = subprocess.run(command, cwd=repo, env=env, text=True,
                                capture_output=True, timeout=300, check=False)
        print(result.stdout[-6000:])
        if result.stderr:
            print(result.stderr[-2000:], file=sys.stderr)
        if not xml.exists():
            raise RuntimeError(f"pytest did not produce test results (exit {result.returncode})")
        document = ElementTree.parse(xml).getroot()
        suite = document if document.tag == "testsuite" else document.find("testsuite")
        if suite is None:
            raise RuntimeError("pytest produced an unreadable JUnit report")
        total = int(suite.get("tests", 0))
        failures = int(suite.get("failures", 0))
        errors = int(suite.get("errors", 0))
        skipped = int(suite.get("skipped", 0))
        passed = total - failures - errors - skipped
        outcomes = {"passed": passed, "failed": failures, "errors": errors,
                    "skipped": skipped, "total": total}
        print(f"Selected pytest cases: {outcomes}")
        if result.returncode or failures or errors or passed < 1:
            raise RuntimeError(f"Selected PR tests did not pass: {outcomes}")
        if total != case["expanded_selected_cases"]:
            raise AssertionError(
                f"Selected pytest cases changed from {case['expanded_selected_cases']} to {total}"
            )
        return outcomes


def recheck(case, run_tests=False):
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
        outcomes = run_selected_tests(repo, case, selected) if run_tests else None
        if os.getenv("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as output:
                output.write(f"### {case['repository']} PR #{case['pr_number']}\n\n"
                             f"Pinned head: `{pr['head_sha']}`. Graph selection: "
                             f"**{len(selected)} test targets**. Verified path: "
                             f"`{' → '.join(path)}`.\n\n")
                if outcomes:
                    output.write(
                        f"Executed **{outcomes['total']} selected pytest cases**: "
                        f"{outcomes['passed']} passed, {outcomes['failed']} failed, "
                        f"{outcomes['errors']} errors, {outcomes['skipped']} skipped.\n\n"
                    )
                    if case["repository"] == "httpie/cli":
                        output.write("Remote `pie.dev` cases were skipped; local cases ran.\n\n")
                else:
                    output.write("Selected tests were not executed in this job.\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", choices=sorted(PATHS))
    parser.add_argument("--run-tests", action="store_true")
    args = parser.parse_args()
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    case = next(item for item in evidence["real_prs"]
                if item["repository"] == args.repository)
    recheck(case, run_tests=args.run_tests)


if __name__ == "__main__":
    main()
