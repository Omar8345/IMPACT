#!/usr/bin/env python3
"""Run controlled mutations and compare IMPACT with simple test-selection baselines."""

from __future__ import annotations

import argparse
import difflib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import graph
import review
import tools
from evaluation.scenarios import SCENARIOS
from repo_parser import changed_functions, parse_diff, parse_repo

FIXTURE = Path(__file__).with_name("fixture")
METHODS = ("filename", "direct_callers", "impact", "all_tests")


def _pytest_id(function_id: str) -> str:
    return tools.pytest_id(function_id)


def _changed_diff(relative_path: str, before: str, after: str) -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{relative_path}",
        tofile=f"b/{relative_path}",
    ))


def _selected_from_impacts(impacts: dict) -> set[str]:
    return {
        _pytest_id(item["id"])
        for affected in impacts.values()
        for item in affected
        if item["is_test"]
    }


def filename_selection(test_ids: set[str], changed_files: set[str]) -> set[str]:
    """Baseline: select tests whose filename contains a changed module name."""
    stems = {Path(name).stem.removeprefix("test_") for name in changed_files}
    return {
        test_id for test_id in test_ids
        if any(stem in Path(test_id.partition("::")[0]).stem.removeprefix("test_")
               for stem in stems)
    }


def score_selection(selected: set[str], failures: set[str], total_tests: int) -> dict:
    detected = selected & failures
    return {
        "selected": len(selected),
        "detected_failures": len(detected),
        "failure_recall": round(len(detected) / len(failures), 4) if failures else 1.0,
        "test_reduction": round(1 - len(selected) / total_tests, 4) if total_tests else 0.0,
        "failure_yield": round(len(detected) / len(selected), 4) if selected else 0.0,
    }


def aggregate(rows: list[dict], method: str) -> dict:
    selected = sum(row["methods"][method]["selected"] for row in rows)
    detected = sum(row["methods"][method]["detected_failures"] for row in rows)
    failures = sum(len(row["failing_tests"]) for row in rows)
    possible = sum(row["total_tests"] for row in rows)
    return {
        "selected_test_runs": selected,
        "detected_failures": detected,
        "total_failures": failures,
        "failure_recall": round(detected / failures, 4) if failures else 1.0,
        "test_reduction": round(1 - selected / possible, 4) if possible else 0.0,
        "failure_yield": round(detected / selected, 4) if selected else 0.0,
    }


def _apply_scenario(repo: Path, scenario: dict) -> str:
    path = repo / scenario["file"]
    before = path.read_text(encoding="utf-8")
    if before.count(scenario["old"]) != 1:
        raise RuntimeError(
            f"{scenario['id']}: expected one exact mutation target, found "
            f"{before.count(scenario['old'])}"
        )
    after = before.replace(scenario["old"], scenario["new"], 1)
    path.write_text(after, encoding="utf-8")
    return _changed_diff(scenario["file"], before, after)


def _assert_pristine(repo: Path) -> tuple[list, set[str]]:
    funcs, _ = parse_repo(repo)
    test_ids = {_pytest_id(item.id) for item in funcs if item.is_test}
    run = review.run_selected_tests(repo, {}, direct_tests=[
        item.id for item in funcs if item.is_test
    ], restricted_env=True)
    bad = {test for test, status in run["statuses"].items()
           if status not in {"passed", "skipped"}}
    if run["returncode"] or bad:
        raise RuntimeError("The pristine benchmark fixture must pass before mutations run.")
    return funcs, test_ids


def run_benchmark(max_hops: int = 4) -> dict:
    if max_hops < 1 or max_hops > 8:
        raise ValueError("max_hops must be between 1 and 8")
    g = graph.connect()
    rows = []

    with tempfile.TemporaryDirectory(prefix="impact-evaluation-") as directory:
        pristine = Path(directory) / "pristine"
        shutil.copytree(FIXTURE, pristine)
        _, all_test_ids = _assert_pristine(pristine)

        for number, scenario in enumerate(SCENARIOS, start=1):
            repo = Path(directory) / scenario["id"]
            shutil.copytree(FIXTURE, repo)
            diff = _apply_scenario(repo, scenario)

            funcs, edges = parse_repo(repo)
            changed = changed_functions(funcs, parse_diff(diff))
            if not changed:
                raise RuntimeError(f"{scenario['id']}: the mutation did not map to a function")
            graph.load(g, funcs, edges)
            direct = {item.id: graph.impact(g, item.id, 1) for item in changed}
            impact = {item.id: graph.impact(g, item.id, max_hops) for item in changed}

            all_run = review.run_selected_tests(
                repo, {}, direct_tests=[item.id for item in funcs if item.is_test],
                restricted_env=True,
            )
            failing = {
                test_id for test_id, status in all_run["statuses"].items()
                if status in {"failed", "error"}
            }
            if not failing:
                raise RuntimeError(f"{scenario['id']}: mutation was not detected by the full suite")

            changed_files = {item.file for item in changed if not item.is_test}
            selections = {
                "filename": filename_selection(all_test_ids, changed_files),
                "direct_callers": _selected_from_impacts(direct),
                "impact": _selected_from_impacts(impact),
                "all_tests": set(all_test_ids),
            }
            methods = {
                name: score_selection(selected, failing, len(all_test_ids))
                for name, selected in selections.items()
            }
            rows.append({
                "number": number,
                "id": scenario["id"],
                "description": scenario["description"],
                "changed_functions": [item.id for item in changed],
                "failing_tests": sorted(failing),
                "total_tests": len(all_test_ids),
                "methods": methods,
            })
            print(
                f"[{number:02}/{len(SCENARIOS)}] {scenario['id']}: "
                f"{len(failing)} failure(s), IMPACT selected "
                f"{methods['impact']['selected']}/{len(all_test_ids)} tests, "
                f"recall {methods['impact']['failure_recall']:.0%}"
            )

    return {
        "schema_version": 1,
        "fixture": {
            "scenarios": len(rows),
            "tests": rows[0]["total_tests"] if rows else 0,
            "max_hops": max_hops,
            "ground_truth": "Failing or erroring tests from a full pytest run for each mutation.",
        },
        "methods": {
            "filename": "Tests with a filename matching the changed production module.",
            "direct_callers": "Test functions one static call edge from the changed function.",
            "impact": f"Tests connected by a FalkorDB CALLS path of 1 to {max_hops} hops.",
            "all_tests": "Every collected test; the ground-truth reference.",
        },
        "aggregate": {name: aggregate(rows, name) for name in METHODS},
        "scenarios": rows,
    }


def markdown_report(result: dict) -> str:
    labels = {
        "filename": "Filename match",
        "direct_callers": "Direct callers",
        "impact": "IMPACT (FalkorDB)",
        "all_tests": "Full suite",
    }
    lines = [
        "# IMPACT test-selection evaluation",
        "",
        "This evaluation applies each mutation independently, runs the complete test suite "
        "to establish ground truth, and then measures which failure-revealing tests each "
        "selection method would have chosen.",
        "",
        "| Method | Failure recall | Test reduction | Failure yield | Selected runs |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for method in METHODS:
        item = result["aggregate"][method]
        lines.append(
            f"| {labels[method]} | {item['failure_recall']:.1%} | "
            f"{item['test_reduction']:.1%} | {item['failure_yield']:.1%} | "
            f"{item['selected_test_runs']} |"
        )
    lines += [
        "",
        f"The fixture contains **{result['fixture']['tests']} tests** and "
        f"**{result['fixture']['scenarios']} controlled mutations**. "
        "Failure recall measures how many tests that failed in the full run were selected. "
        "Test reduction measures how many test executions were avoided. Failure yield is "
        "the share of selected tests that exposed the injected defect; passing selected tests "
        "can still be relevant to the changed behavior.",
        "",
        "## Per-mutation results",
        "",
        "| Mutation | Full-suite failures | Filename recall | Direct recall | IMPACT recall | IMPACT selected |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in result["scenarios"]:
        methods = row["methods"]
        lines.append(
            f"| `{row['id']}` | {len(row['failing_tests'])} | "
            f"{methods['filename']['failure_recall']:.0%} | "
            f"{methods['direct_callers']['failure_recall']:.0%} | "
            f"{methods['impact']['failure_recall']:.0%} | "
            f"{methods['impact']['selected']}/{row['total_tests']} |"
        )
    lines += [
        "",
        "## Reproduce it",
        "",
        "Start FalkorDB, install the project requirements, and run:",
        "",
        "```bash",
        "python evaluation/run.py",
        "```",
        "",
        "The command rewrites `evaluation/results.json`, the published HTML summary, and this "
        "report. The fixture uses synthetic data and the benchmark does not call an LLM.",
        "",
        "## Scope",
        "",
        "This is a controlled benchmark of static Python call-graph test selection. It does "
        "not measure every Python pattern or claim production-wide accuracy. Dynamic dispatch, "
        "reflection, native extensions, and runtime imports can hide relationships from static "
        "analysis. The committed scenarios, fixture, mutations, raw results, and scoring code "
        "are included so the numbers can be inspected and rerun.",
        "",
    ]
    return "\n".join(lines)


def html_report(result: dict) -> str:
    labels = {
        "filename": "Filename match",
        "direct_callers": "Direct callers",
        "impact": "IMPACT · FalkorDB",
        "all_tests": "Full suite",
    }
    cards = []
    for method in METHODS:
        item = result["aggregate"][method]
        featured = " featured" if method == "impact" else ""
        cards.append(f"""
          <article class="method{featured}">
            <span>{labels[method]}</span>
            <strong>{item['failure_recall']:.1%}</strong>
            <small>failure recall</small>
            <div><b>{item['test_reduction']:.1%}</b> fewer runs</div>
          </article>""")
    rows = []
    for row in result["scenarios"]:
        item = row["methods"]["impact"]
        rows.append(f"""
          <tr>
            <td><code>{row['id']}</code><small>{row['description']}</small></td>
            <td>{len(row['failing_tests'])}</td>
            <td>{item['selected']} / {row['total_tests']}</td>
            <td><span class="pass">{item['failure_recall']:.0%}</span></td>
          </tr>""")
    impact = result["aggregate"]["impact"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="description" content="Reproducible IMPACT test-selection benchmark">
  <title>IMPACT · Evaluation</title>
  <style>
    :root {{ color-scheme: dark; --bg:#0d0f10; --panel:#151819; --line:#303537;
      --text:#f4f4f0; --muted:#989f9f; --red:#ff4f61; --green:#58d1a5; }}
    * {{ box-sizing:border-box }}
    body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace; }}
    body:before {{ content:""; position:fixed; inset:0; pointer-events:none; opacity:.14;
      background-image:radial-gradient(#778 1px,transparent 1px); background-size:22px 22px; }}
    main {{ position:relative; width:min(1120px,calc(100% - 32px)); margin:auto; padding:64px 0 80px; }}
    .eyebrow {{ color:var(--red); letter-spacing:.18em; font-size:12px; font-weight:800; text-transform:uppercase; }}
    h1 {{ max-width:850px; margin:15px 0 14px; font:800 clamp(38px,7vw,76px)/.98 ui-sans-serif,system-ui; letter-spacing:-.055em; }}
    .lede {{ max-width:760px; color:#c2c7c6; font-size:17px; }}
    .hero {{ border-bottom:1px solid var(--line); padding-bottom:42px; }}
    .headline {{ display:flex; gap:18px; flex-wrap:wrap; margin-top:30px; }}
    .headline div {{ border-left:2px solid var(--red); padding:5px 18px; }}
    .headline strong {{ display:block; font-size:28px; }} .headline small {{ color:var(--muted); }}
    h2 {{ margin:48px 0 18px; font:700 25px/1.2 ui-sans-serif,system-ui; }}
    .methods {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }}
    .method {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:20px; }}
    .method.featured {{ border-color:var(--red); box-shadow:inset 0 0 0 1px #ff4f6144; }}
    .method span,.method small {{ display:block; color:var(--muted); }}
    .method strong {{ display:block; margin:12px 0 0; font:800 34px/1 ui-sans-serif,system-ui; }}
    .method div {{ margin-top:18px; border-top:1px solid var(--line); padding-top:12px; }}
    .method.featured span,.method.featured strong {{ color:var(--red); }}
    .note {{ margin-top:14px; padding:16px 18px; border:1px solid var(--line); background:#111314; color:#bbc0bf; }}
    table {{ width:100%; border-collapse:collapse; background:var(--panel); border:1px solid var(--line); }}
    th,td {{ padding:14px 16px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-size:11px; letter-spacing:.09em; text-transform:uppercase; }}
    td small {{ display:block; margin-top:4px; color:var(--muted); }} code {{ color:#fff; }}
    .pass {{ color:var(--green); font-weight:800; }}
    a {{ color:var(--red); }} footer {{ margin-top:30px; color:var(--muted); }}
    @media (max-width:800px) {{ .methods {{ grid-template-columns:1fr 1fr; }} table {{ font-size:12px; }} }}
    @media (max-width:520px) {{ .methods {{ grid-template-columns:1fr; }} th:nth-child(2),td:nth-child(2) {{ display:none; }} }}
  </style>
</head>
<body><main>
  <section class="hero">
    <div class="eyebrow">Graph intelligence / evaluation 001</div>
    <h1>Does the graph pick the tests that expose the bug?</h1>
    <p class="lede">Every mutation runs alone. The complete pytest suite establishes ground truth. Then filename matching, direct callers, and IMPACT compete to select the failure-revealing tests.</p>
    <div class="headline">
      <div><strong>{result['fixture']['scenarios']}</strong><small>controlled mutations</small></div>
      <div><strong>{result['fixture']['tests']}</strong><small>tests in the fixture</small></div>
      <div><strong>{impact['detected_failures']}/{impact['total_failures']}</strong><small>failures found by IMPACT</small></div>
      <div><strong>{impact['test_reduction']:.1%}</strong><small>fewer test executions</small></div>
    </div>
  </section>
  <h2>Selection methods</h2>
  <section class="methods">{''.join(cards)}</section>
  <div class="note"><b>Read this precisely.</b> Failure recall counts tests that failed or errored in the full run and were also selected. A selected passing test can still cover relevant behavior, so failure yield is not general relevance precision.</div>
  <h2>Every mutation</h2>
  <table><thead><tr><th>Injected defect</th><th>Full-suite failures</th><th>IMPACT selected</th><th>Failure recall</th></tr></thead>
  <tbody>{''.join(rows)}</tbody></table>
  <footer>Controlled static-analysis benchmark · synthetic fixture · no LLM used · <a href="../evaluation.md">method and limitations</a> · <a href="results.json">raw JSON</a></footer>
</main></body></html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hops", type=int, default=4)
    parser.add_argument("--json", default="evaluation/results.json")
    parser.add_argument("--web-json", default="docs/evaluation/results.json")
    parser.add_argument("--markdown", default="docs/evaluation.md")
    parser.add_argument("--html", default="docs/evaluation/index.html")
    args = parser.parse_args()

    result = run_benchmark(args.hops)
    json_path = Path(args.json)
    web_json_path = Path(args.web_json)
    markdown_path = Path(args.markdown)
    html_path = Path(args.html)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    web_json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(result, indent=2) + "\n"
    json_path.write_text(encoded, encoding="utf-8")
    web_json_path.write_text(encoded, encoding="utf-8")
    markdown_path.write_text(markdown_report(result), encoding="utf-8")
    html_path.write_text(html_report(result), encoding="utf-8")
    impact = result["aggregate"]["impact"]
    print(
        f"\nIMPACT: {impact['failure_recall']:.1%} failure recall with "
        f"{impact['test_reduction']:.1%} fewer test executions."
    )
    print(f"Wrote {json_path}, {markdown_path}, {html_path}, and {web_json_path}")


if __name__ == "__main__":
    main()
