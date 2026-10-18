# How IMPACT works

Think of the project as a chain of six small jobs:

1. **Read the code.** `repo_parser.py` uses Python's built-in `ast` parser. It
   records each function, its file and line range, and calls it can resolve
   through imports or local names. It does not run the repository's code.
2. **Store relationships.** `graph.py` writes `File` and `Function` nodes into
   FalkorDB. `DEFINES` links files to functions; `CALLS` links caller to callee.
3. **Find the change.** `main.py review` reads a Git diff and finds functions
   whose line ranges overlap edited lines. Unchanged context in a diff hunk
   does not count as a change.
4. **Ask the graph.** The agent traverses `CALLS` relationships backward from
   each changed function. If `checkout` calls `total`, and `total` calls the
   changed `apply_coupon`, `checkout` may be affected. The path is the proof of
   that connection.
5. **Act and explain.** The agent selects reachable tests and directly changed
   tests. With `--run-tests`
   it runs them and records actual outcomes. It prints Markdown and generates
   an interactive HTML path explorer. With `--llm`, OpenRouter queries graph
   tools and chooses a changed function and eligible test to inspect first.
   When the selected tests finish, the application derives a verdict from their
   observed statuses. The model then chooses a bounded next action and may
   suggest an unverified fix for a failing test. No suggested patch is applied.
   The app checks those choices against graph results before using them.
   For a trusted GitHub PR, `--compare-base` reruns the same selected tests on
   the exact base commit and reports outcomes that appeared or disappeared.
6. **Bring in company context when supplied.** `company.py` loads a curated
   manifest of owners and source documents into the same FalkorDB graph. The
   `company` command and PR review query those links to suggest a reviewer and
   show the decision, ticket, or chat record behind a changed function.

```text
Git diff ──> changed function ──> FalkorDB traversal ──> selected tests
                                 │                         │
                                 └──> paths ───────────────┴──> report + UI
```

## Why a graph database?

A changed function can have callers, callers of callers, and tests several
steps away. FalkorDB stores those relationships directly and returns the path
for each answer. The product depends on those paths for impact analysis and
test selection; the visual page is a presentation of graph results.

## What the agent does not know

Static calls show *reachability*, not a guaranteed bug. The parser intentionally
does not guess about dynamic calls (`getattr`, dependency injection, callbacks,
monkey-patching), and code that calls a function can still pass after a change.
That is why the optional test run is a separate verification step. A missing
edge means the parser could not prove that call; it is not proof that no impact
exists.

## How to explain it in a demo

Point to `shop/pricing.py::apply_coupon`, then to the four-hop path ending at
`test_checkout_large_coupon`. Say: “The graph found that this test reaches the
changed function through these calls. The agent chose that test, ran it, and
confirmed the coupon regression. The normal coupon test still passes.”
