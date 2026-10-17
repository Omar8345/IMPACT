# Understand IMPACT in 10 minutes

You do not need to be an AI engineer to explain this project. The core is a
question: **if one function changes, which other functions and tests depend on
it?**

## The example

`shop/pricing.py::apply_coupon` should never return a negative total. The demo
contains an intentional bug: a $30 coupon applied to a $20 item produces -$10.
Checkout refuses to charge a negative amount, while a receipt shows -$10.

Open `demo_checkout/shop/pricing.py` and find that one changed line. Then look
at `demo_checkout/coupon_bug.patch`: it is the saved pull request diff. The
review command reads that diff to discover which function changed.

## Why FalkorDB matters

Imagine each function as a dot. Draw an arrow when one function calls another.
For example:

```text
checkout_cart -> build_order_summary -> calculate_total -> apply_coupon
```

Those dots and arrows live in FalkorDB as `Function` nodes and `CALLS` edges.
The agent asks FalkorDB to follow arrows *backward* from `apply_coupon`. It finds
the functions that depend on the changed one, even several steps away. It then
selects test functions found on those paths. If FalkorDB is removed, the agent
cannot answer the impact question or select tests.

The graph also stores `File` nodes connected to their functions by `DEFINES`
edges. See [graph_queries.md](graph_queries.md) for the actual Cypher.

## What each file does

| File | Plain English job |
| --- | --- |
| `repo_parser.py` | Reads Python source and discovers functions and calls. |
| `graph.py` | Saves dots and arrows in FalkorDB and asks graph questions. |
| `company.py` | Links owners, teams, and source documents to the code graph. |
| `review.py` | Selects tests, runs them if requested, and writes the report. |
| `tools.py` | Exposes graph questions as callable agent tools. |
| `main.py` | Provides the `index`, `doctor`, `review`, `company`, and `pr` commands. |
| `github_pr.py` | Fetches a public PR and its exact head commit. |
| `impact_template.html` | Defines the interactive report's look and behavior. |

## Follow one run

1. `index` parses the 9 demo functions and 8 calls, then writes them to FalkorDB.
2. `review` reads the saved diff and sees that `apply_coupon` changed.
3. FalkorDB returns 7 callers within four hops, including 3 tests.
4. `--run-tests` runs those 3 tests: the normal coupon passes, while the two
   large-coupon tests fail in different ways.
5. The report and HTML page show paths and actual test outcomes. A path means
   *possible impact*. The test result is the evidence of an actual problem.

## Questions a judge may ask

**Why use a graph instead of asking an LLM to read the code?** The call paths
are explicit relationships queried from FalkorDB. The LLM, when enabled,
chooses a review priority from graph-verified options; it cannot invent a path
or test ID that the app then treats as evidence.

**What action does the agent take?** It selects tests from graph paths and runs
them with `--run-tests`. The result changes the review from a prediction to a
verified finding.

**What does PageRank do here?** It ranks functions that many other functions
depend on. `doctor` confirms the algorithm works on the deployed graph.

**What are the limits?** The parser understands common explicit Python calls.
It cannot reliably infer dynamic imports, monkey patches, or every runtime
dispatch. An unshown path is therefore not proof that a change is harmless.

**Where is the AI?** `--llm` asks an OpenRouter model to query the graph, then
choose which changed function and eligible test deserve attention first. The
app validates the choice, runs that test first if requested, and labels its
result separately from the model's prediction. Graph analysis still works
without a model.

**How does the Company Brain part work?** The optional `company.json` manifest
connects the fictional team's people, decision, ticket, and chat record to
specific code. The same graph used for call paths now answers who owns a
changed function and which source explains the expected behavior. The review
suggests that owner and cites the source. Rerun `index --company-file` after
changing a source to refresh the graph.

## Try it yourself

Run the commands in [README.md](../README.md). Click different dots in the
HTML page to see their paths. Then change one line in `demo_checkout`, re-index,
and make a new diff to see how the affected paths change.
