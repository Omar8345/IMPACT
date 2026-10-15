"""FalkorDB layer: load the call graph and run the queries the agent's tools use."""
import os

from falkordb import FalkorDB

GRAPH = os.getenv("FALKORDB_GRAPH", "pr_impact")


def connect():
    host = os.getenv("FALKORDB_HOST", "localhost")
    port = int(os.getenv("FALKORDB_PORT", "6379"))
    db = FalkorDB(
        host=host,
        port=port,
        username=os.getenv("FALKORDB_USERNAME") or None,
        password=os.getenv("FALKORDB_PASSWORD") or None,
        ssl=os.getenv("FALKORDB_SSL", "false").lower() in ("1", "true", "yes"),
        socket_connect_timeout=8,
        socket_timeout=30,
    )
    try:
        db.connection.ping()
    except Exception as exc:
        raise ConnectionError(
            f"Cannot connect to FalkorDB at {host}:{port}. Check FALKORDB_HOST, "
            "FALKORDB_PORT, FALKORDB_USERNAME, FALKORDB_PASSWORD, and "
            "FALKORDB_SSL in this terminal."
        ) from exc
    return db.select_graph(GRAPH)


def _chunks(items, n=500):
    for i in range(0, len(items), n):
        yield items[i:i + n]


def load(g, funcs, edges):
    try:
        g.delete()
    except Exception:
        pass  # graph did not exist yet
    try:
        g.query("CREATE INDEX FOR (f:Function) ON (f.id)")
    except Exception:
        pass

    rows = [dict(id=f.id, name=f.name, qual=f.qualname, file=f.file,
                 start=f.start, end=f.end, is_test=f.is_test) for f in funcs]
    for chunk in _chunks(rows):
        g.query("""
            UNWIND $rows AS r
            MERGE (fl:File {path: r.file})
            MERGE (fn:Function {id: r.id})
            SET fn.name = r.name, fn.qualname = r.qual, fn.file = r.file,
                fn.start = r.start, fn.end = r.end, fn.is_test = r.is_test
            MERGE (fl)-[:DEFINES]->(fn)
        """, {"rows": chunk})

    for chunk in _chunks([{"a": a, "b": b} for a, b in edges]):
        g.query("""
            UNWIND $rows AS r
            MATCH (a:Function {id: r.a}), (b:Function {id: r.b})
            MERGE (a)-[:CALLS]->(b)
        """, {"rows": chunk})


def find_function(g, name, limit=10):
    res = g.query(f"""
        MATCH (f:Function)
        WHERE f.name = $n OR f.id CONTAINS $n
        RETURN f.id, f.start, f.end LIMIT {int(limit)}
    """, {"n": name})
    return [{"id": r[0], "start": r[1], "end": r[2]} for r in res.result_set]


def impact(g, fid, max_hops=4):
    """Everything that reaches `fid` through CALLS edges, with the shortest path found for each."""
    if not 1 <= int(max_hops) <= 8:
        raise ValueError("max_hops must be between 1 and 8")
    res = g.query(f"""
        MATCH p = (c:Function)-[:CALLS*1..{int(max_hops)}]->(t:Function {{id: $id}})
        RETURN c.id, c.is_test, length(p), [n IN nodes(p) | n.id]
    """, {"id": fid})
    best = {}
    for cid, is_test, hops, path in res.result_set:
        if cid not in best or hops < best[cid]["hops"]:
            best[cid] = {"id": cid, "is_test": bool(is_test), "hops": hops, "path": path}
    return sorted(best.values(), key=lambda r: (r["hops"], r["id"]))


def risk_rank(g, limit=10):
    """Most depended-on functions, by PageRank over CALLS edges."""
    res = g.query(f"""
        CALL algo.pageRank('Function', 'CALLS') YIELD node, score
        RETURN node.id, score ORDER BY score DESC LIMIT {int(limit)}
    """)
    return [{"id": r[0], "score": round(r[1], 5)} for r in res.result_set]


def call_path(g, a, b):
    res = g.query("""
        MATCH (a:Function {id: $a}), (b:Function {id: $b})
        WITH shortestPath((a)-[:CALLS*]->(b)) AS p
        RETURN [n IN nodes(p) | n.id]
    """, {"a": a, "b": b})
    return res.result_set[0][0] if res.result_set else None


def health(g):
    """Exercise the central graph query and optional algorithm tools."""
    counts = g.query("MATCH (f:Function) RETURN count(f)").result_set[0][0]
    edges = g.query("MATCH ()-[r:CALLS]->() RETURN count(r)").result_set[0][0]
    result = {"functions": counts, "call_edges": edges}
    if counts:
        result["pagerank_top"] = risk_rank(g, 1)
    sample = g.query("MATCH (a:Function)-[:CALLS]->(b:Function) RETURN a.id, b.id LIMIT 1").result_set
    if sample:
        result["sample_path"] = call_path(g, sample[0][0], sample[0][1])
    return result
