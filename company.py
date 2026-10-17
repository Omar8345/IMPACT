"""Connect engineering ownership and source documents to the code graph."""

import hashlib
import json
from pathlib import Path


def read_manifest(repo, manifest):
    repo = Path(repo).resolve()
    data = json.loads(Path(manifest).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Company manifest must be a JSON object")
    for source in data.get("knowledge", []):
        relative = Path(source["path"])
        full = (repo / relative).resolve()
        if not full.is_relative_to(repo) or not full.is_file():
            raise ValueError(f"Knowledge source must be a file inside the repo: {relative}")
        source["content"] = full.read_text(encoding="utf-8")
        source["sha256"] = hashlib.sha256(source["content"].encode()).hexdigest()
    return data


def validate_manifest(repo, manifest, funcs):
    data = read_manifest(repo, manifest)
    functions = {f.id for f in funcs}
    files = {f.file for f in funcs}
    teams = {t["id"] for t in data.get("teams", [])}
    for person in data.get("people", []):
        if person["team"] not in teams:
            raise ValueError(f"Unknown team for {person['id']}")
        if set(person.get("owns", [])) - files:
            raise ValueError(f"Unknown owned file for {person['id']}")
    for source in data.get("knowledge", []):
        if set(source.get("functions", [])) - functions:
            raise ValueError(f"Unknown function in knowledge source {source['id']}")
    return data


def sync(g, data):
    """Refresh company context in the same FalkorDB graph as the call graph."""

    for label in ("Person", "Team", "Knowledge"):
        g.query(f"MATCH (n:{label}) DETACH DELETE n")

    for team in data.get("teams", []):
        g.query("MERGE (t:Team {id: $id}) SET t.name = $name", team)
    for person in data.get("people", []):
        g.query("""
            MATCH (t:Team {id: $team})
            MERGE (p:Person {id: $id}) SET p.name = $name
            MERGE (p)-[:MEMBER_OF]->(t)
        """, {"team": person["team"], "id": person["id"], "name": person["name"]})
        for file in person.get("owns", []):
            g.query("""
                MATCH (p:Person {id: $person}), (f:File {path: $file})
                MERGE (p)-[:OWNS]->(f)
            """, {"person": person["id"], "file": file})
    for source in data.get("knowledge", []):
        g.query("""
            MERGE (k:Knowledge {id: $id})
            SET k.title = $title, k.kind = $kind, k.path = $path,
                k.content = $content, k.sha256 = $sha256
        """, {key: source[key] for key in ("id", "title", "kind", "path", "content", "sha256")})
        for fid in source.get("functions", []):
            g.query("""
                MATCH (k:Knowledge {id: $source}), (f:Function {id: $function})
                MERGE (k)-[:ABOUT]->(f)
            """, {"source": source["id"], "function": fid})
    return len(data.get("people", [])), len(data.get("knowledge", []))


def context(g, function_id):
    """Return graph-backed owners and source records for a function."""
    owner_rows = g.query("""
        MATCH (fn:Function {id: $id})<-[:DEFINES]-(file:File)<-[:OWNS]-(p:Person)-[:MEMBER_OF]->(t:Team)
        RETURN DISTINCT p.name, t.name, file.path ORDER BY p.name
    """, {"id": function_id}).result_set
    source_rows = g.query("""
        MATCH (fn:Function {id: $id})<-[:ABOUT]-(k:Knowledge)
        RETURN k.id, k.kind, k.title, k.path, k.content, k.sha256 ORDER BY k.id
    """, {"id": function_id}).result_set
    return {"function": function_id,
            "owners": [{"name": n, "team": t, "file": f} for n, t, f in owner_rows],
            "sources": [{"id": i, "kind": kind, "title": title, "path": path,
                         "content": content, "sha256": sha}
                        for i, kind, title, path, content, sha in source_rows]}


def report(contexts):
    if not any(c["owners"] or c["sources"] for c in contexts):
        return ""
    lines = ["## Engineering context", ""]
    for item in contexts:
        lines.extend([f"### `{item['function']}`", ""])
        if item["owners"]:
            lines.append("**Suggested reviewers:** " + ", ".join(
                f"{o['name']} ({o['team']}; owns `{o['file']}`)" for o in item["owners"]))
        else:
            lines.append("**Suggested reviewers:** No owner recorded.")
        for source in item["sources"]:
            lines.append(f"- {source['kind'].title()}: **{source['title']}** "
                         f"— `{source['path']}` (source ID `{source['id']}`)")
        lines.append("")
    lines.append("Ownership and sources come from FalkorDB links. Check the cited files before acting.")
    return "\n".join(lines)
