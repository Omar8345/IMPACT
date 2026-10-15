"""IMPACT command line interface."""
import argparse
import subprocess
from pathlib import Path

def cmd_index(a):
    print("IMPACT sample checkout: " + str(Path(a.repo).resolve()))

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
