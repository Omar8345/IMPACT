"""IMPACT command line interface."""
import argparse
import subprocess
from pathlib import Path
from repo_parser import parse_repo, parse_diff, changed_functions
import graph

def cmd_index(a):
    funcs, edges = parse_repo(a.repo)
    g = graph.connect()
    graph.load(g, funcs, edges)
    print(f"Indexed {len(funcs)} functions and {len(edges)} call edges into FalkorDB.")

def main():
    p = argparse.ArgumentParser(description="PR impact agent")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("index")
    s.add_argument("repo")
    s.set_defaults(fn=cmd_index)
    a = p.parse_args()
    a.fn(a)

if __name__ == "__main__":
    main()
