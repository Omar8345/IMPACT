"""IMPACT command line interface."""
import argparse
import subprocess
from pathlib import Path
from repo_parser import parse_repo, parse_diff, changed_functions
import graph
import review

def cmd_index(a):
    funcs, edges = parse_repo(a.repo)
    g = graph.connect()
    graph.load(g, funcs, edges)
    print(f"Indexed {len(funcs)} functions and {len(edges)} call edges into FalkorDB.")

def cmd_review(a):
    diff = Path(a.diff_file).read_text(encoding="utf-8") if a.diff_file else subprocess.run(["git", "-C", a.repo, "diff", a.base], capture_output=True, text=True, check=True).stdout
    funcs, _ = parse_repo(a.repo)
    changed = changed_functions(funcs, parse_diff(diff))
    if not changed:
        print("No Python functions changed in this diff.")
        return
    impacts = review.compute_impacts(changed, a.hops)
    decision = review.llm_decision(changed, diff, impacts, [f.id for f in changed if f.is_test]) if a.llm else None
    run = review.run_selected_tests(a.repo, impacts, direct_tests=[f.id for f in changed if f.is_test], priority_test=decision["priority_test"] if decision else None) if a.run_tests else None
    report = decision["report"] + "\n\n" + review.graph_evidence_section(changed, impacts) if decision else review.deterministic_report(changed, impacts, a.repo, run)
    print(report)
    if a.report:
        Path(a.report).write_text(report + "\n", encoding="utf-8")
    return report

def main():
    p = argparse.ArgumentParser(description="PR impact agent")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("index")
    s.add_argument("repo")
    s.set_defaults(fn=cmd_index)
    s = sub.add_parser("review")
    s.add_argument("repo")
    s.add_argument("--base", default="HEAD~1")
    s.add_argument("--diff-file")
    s.add_argument("--hops", type=int, default=4)
    s.add_argument("--run-tests", action="store_true")
    s.add_argument("--report")
    s.add_argument("--llm", action="store_true")
    s.set_defaults(fn=cmd_review)
    a = p.parse_args()
    a.fn(a)

if __name__ == "__main__":
    main()
