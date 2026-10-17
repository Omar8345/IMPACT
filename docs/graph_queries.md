# Graph model and Cypher queries

## Model

| Node or edge | Stored information | Purpose |
| --- | --- | --- |
| `File` | `path` | Source file identity |
| `Function` | `id`, `name`, `qualname`, `file`, `start`, `end`, `is_test` | Function or test identity |
| `(:File)-[:DEFINES]->(:Function)` | — | Which file defines a function |
| `(:Function)-[:CALLS]->(:Function)` | — | Caller to callee relationship |
| `Person`, `Team` | IDs and names | Engineering ownership |
| `Knowledge` | ID, type, title, source path, content hash, content | Decision, ticket, or chat source |
| `(:Person)-[:MEMBER_OF]->(:Team)` | — | Team membership |
| `(:Person)-[:OWNS]->(:File)` | — | Who should review a file |
| `(:Knowledge)-[:ABOUT]->(:Function)` | — | Which source explains a function |

IDs use `relative/path.py::qualname`, such as
`tests/test_checkout.py::CheckoutTests.test_checkout_large_coupon`.

## Load functions and call edges

`graph.py` sends batches of rows as query parameters. These are the essential
Cypher patterns:

```cypher
UNWIND $rows AS r
MERGE (fl:File {path: r.file})
MERGE (fn:Function {id: r.id})
SET fn.name = r.name, fn.qualname = r.qual, fn.file = r.file,
    fn.start = r.start, fn.end = r.end, fn.is_test = r.is_test
MERGE (fl)-[:DEFINES]->(fn)
```

```cypher
UNWIND $rows AS r
MATCH (a:Function {id: r.a}), (b:Function {id: r.b})
MERGE (a)-[:CALLS]->(b)
```

## Find potential impact

The direction is important. `CALLS` points from caller to callee, so the
query finds callers whose path ends at the changed function:

```cypher
MATCH p = (caller:Function)-[:CALLS*1..4]->(changed:Function {id: $id})
RETURN caller.id, caller.is_test, length(p), [n IN nodes(p) | n.id]
```

The Python layer keeps the shortest returned path for each caller. A test is
selected when its `is_test` flag is true. The query result is also the evidence
shown in the report and UI.

## Other exposed graph tools

The MCP server and optional LLM also expose these queries:

```cypher
CALL algo.pageRank('Function', 'CALLS') YIELD node, score
RETURN node.id, score ORDER BY score DESC LIMIT 10
```

```cypher
MATCH (a:Function {id: $a}), (b:Function {id: $b})
WITH shortestPath((a)-[:CALLS*]->(b)) AS p
RETURN [n IN nodes(p) | n.id]
```

The impact traversal, PageRank, and shortest-path helper have been exercised
against FalkorDB Cloud with the synthetic demo.

## Company context

When a company manifest is provided, `company.py` links its people and source
documents to the same `File` and `Function` nodes. A review asks FalkorDB who
owns the changed function's file:

```cypher
MATCH (fn:Function {id: $id})<-[:DEFINES]-(file:File)<-[:OWNS]-(p:Person)-[:MEMBER_OF]->(t:Team)
RETURN DISTINCT p.name, t.name, file.path ORDER BY p.name
```

It also retrieves cited decisions, tickets, and chats:

```cypher
MATCH (fn:Function {id: $id})<-[:ABOUT]-(k:Knowledge)
RETURN k.id, k.kind, k.title, k.path, k.content, k.sha256 ORDER BY k.id
```

The manifest and local files are an explicit demo input. The app does not
invent ownership or claim to have connected to real company systems.
