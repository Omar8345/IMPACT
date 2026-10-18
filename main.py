"""PR impact agent. Usage:
    python main.py index  <repo>
    python main.py review <repo> --base HEAD~1 [--llm]
    python main.py review <repo> --diff-file change.patch
    python main.py pr https://github.com/owner/repo/pull/123
    python main.py mcp
"""
import argparse
import subprocess
from pathlib import Path

import graph
import github_pr
import review
import company
from repo_parser import changed_functions, parse_diff, parse_repo


def cmd_index(a):
    funcs, edges = parse_repo(a.repo)
    company_data = company.validate_manifest(a.repo, a.company_file, funcs) if a.company_file else None
    print(f"Parsed {len(funcs)} functions and {len(edges)} call edges. Connecting to FalkorDB...", flush=True)
    g = graph.connect()
    graph.load(g, funcs, edges)
    print(f"Indexed {len(funcs)} functions and {len(edges)} call edges into FalkorDB.")
    if company_data:
        people, sources = company.sync(g, company_data)
        print(f"Connected {people} people and {sources} source documents to the code graph.")


def cmd_review(a):
    if a.diff_file:
        diff = Path(a.diff_file).read_text(encoding="utf-8")
    else:
        diff = subprocess.run(["git", "-C", a.repo, "diff", a.base],
                              capture_output=True, text=True, check=True).stdout
    return produce_review(a.repo, diff, a)


def produce_review(repo, diff, a):
    funcs, _ = parse_repo(repo)
    changed = changed_functions(funcs, parse_diff(diff))
    if not changed:
        print("No Python functions changed in this diff.")
        return
    print(f"Changed functions: {', '.join(f.id for f in changed)}\n")

    impacts = review.compute_impacts(changed, a.hops)
    direct_tests = [f.id for f in changed if f.is_test]
    decision = None
    if a.llm:
        try:
            decision = review.llm_decision(changed, diff, impacts, direct_tests)
        except RuntimeError as exc:
            print(f"Optional AI review unavailable: {exc}\nUsing the graph review instead.\n")
    test_run = (review.run_selected_tests(
        repo, impacts, direct_tests=direct_tests,
        priority_test=decision["priority_test"] if decision else None,
        test_command=a.test_command,
        restricted_env=getattr(a, "restricted_env", False)) if a.run_tests else None)
    if decision and test_run is not None:
        decision["followup"] = review.review_followup(changed, diff, impacts, decision, test_run)
    if decision:
        report = decision["report"].rstrip()
        report += "\n\n" + review.graph_evidence_section(changed, impacts)
        if test_run is not None:
            report += "\n\n" + review.verification_section(test_run).rstrip()
            report += "\n\n" + review.followup_section(decision["followup"])
    else:
        report = review.deterministic_report(changed, impacts, repo, test_run)
    g = graph.connect()
    contexts = [company.context(g, f.id) for f in changed]
    company_note = company.report(contexts)
    if company_note:
        report += "\n\n" + company_note
    print(report)
    if a.report:
        Path(a.report).write_text(report + "\n", encoding="utf-8")
        print(f"Report written to {a.report}")
    review.write_html(changed, impacts, a.html, test_run, decision, contexts)
    print(f"\nGraph written to {a.html}")
    return report


def cmd_pr(a):
    pr = github_pr.get_pr(a.url)
    a.restricted_env = True
    print(f"Fetching {pr['url']} at {pr['head_sha'][:12]}...", flush=True)
    with github_pr.checkout_pr(pr) as (repo, diff):
        funcs, edges = parse_repo(repo)
        company_data = (company.validate_manifest(repo, Path(repo) / a.company_file, funcs)
                        if a.company_file else None)
        print(f"Parsed {len(funcs)} functions and {len(edges)} call edges. Connecting to FalkorDB...", flush=True)
        g = graph.connect()
        graph.load(g, funcs, edges)
        print(f"Indexed PR head into FalkorDB graph {graph.GRAPH}.")
        if company_data:
            people, sources = company.sync(g, company_data)
            print(f"Connected {people} people and {sources} source documents.")
        report = produce_review(repo, diff, a)
    if a.post_comment:
        if not report:
            print("No Python function impact report to post.")
            return
        comment = f"<!-- impact-pr-review -->\n## IMPACT review\n\n{report.rstrip()}\n"
        url = github_pr.post_comment(pr, comment)
        print(f"Posted PR comment: {url}")


def cmd_mcp(a):
    import mcp_server
    mcp_server.run()


def cmd_doctor(a):
    result = graph.health(graph.connect())
    print(f"FalkorDB OK: {result['functions']} functions, {result['call_edges']} CALLS edges")
    if result.get("pagerank_top"):
        print(f"PageRank OK: {result['pagerank_top'][0]['id']}")
    if result.get("sample_path"):
        print("Shortest path OK: " + " -> ".join(result["sample_path"]))


def cmd_company(a):
    item = company.context(graph.connect(), a.function_id)
    note = company.report([item])
    print(note or f"No company context recorded for {a.function_id}.")


def main():
    p = argparse.ArgumentParser(description="PR impact agent")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("index", help="parse a repo and load its call graph into FalkorDB")
    s.add_argument("repo")
    s.add_argument("--company-file", help="JSON manifest connecting owners and source documents to code")
    s.set_defaults(fn=cmd_index)

    s = sub.add_parser("review", help="explain what a diff affects")
    s.add_argument("repo")
    s.add_argument("--base", default="HEAD~1", help="git ref to diff against")
    s.add_argument("--diff-file", help="use a saved unified diff instead of git")
    s.add_argument("--llm", action="store_true", help="let an OpenRouter model use graph tools (needs OPENROUTER_API_KEY)")
    s.add_argument("--run-tests", action="store_true", help="run graph-selected tests (pytest or unittest)")
    s.add_argument("--test-command", help="custom runner with {test} or {unittest}; requires --run-tests")
    s.add_argument("--hops", type=int, default=4)
    s.add_argument("--html", default="impact.html")
    s.add_argument("--report", help="save Markdown review for a PR comment or artifact")
    s.set_defaults(fn=cmd_review)

    s = sub.add_parser("pr", help="review a public GitHub pull request URL")
    s.add_argument("url", help="https://github.com/owner/repo/pull/123")
    s.add_argument("--llm", action="store_true", help="let an OpenRouter model use graph tools")
    s.add_argument("--run-tests", action="store_true", help="run selected tests from the PR checkout")
    s.add_argument("--test-command", help="custom runner with {test} or {unittest}; requires --run-tests")
    s.add_argument("--post-comment", action="store_true", help="post the report to the PR with gh authentication")
    s.add_argument("--company-file", help="manifest path inside the PR checkout")
    s.add_argument("--hops", type=int, default=4)
    s.add_argument("--html", default="impact.html")
    s.add_argument("--report", default="impact-report.md")
    s.set_defaults(fn=cmd_pr)

    s = sub.add_parser("mcp", help="run the MCP server")
    s.set_defaults(fn=cmd_mcp)

    s = sub.add_parser("doctor", help="check FalkorDB queries and graph algorithms")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("company", help="show source-backed owners and decisions for a function")
    s.add_argument("function_id", help="path/to/file.py::function_name")
    s.set_defaults(fn=cmd_company)

    a = p.parse_args()
    if getattr(a, "test_command", None) and not a.run_tests:
        p.error("--test-command requires --run-tests")
    a.fn(a)


if __name__ == "__main__":
    main()
