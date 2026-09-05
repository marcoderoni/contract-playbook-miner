#!/usr/bin/env python3
"""Orchestrator: run the full pipeline with one command.

    python3 run.py --docs ./Contracts --internal "Jane Doe,John Smith" --out ./out

Steps: sort (optional, needs rules.json) -> extract -> thematic -> (skeleton) playbook.
Everything offline, stdlib only.
"""
import argparse, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "src")

def run(script, *args):
    cmd = [sys.executable, os.path.join(SRC, script), *map(str, args)]
    print("»", " ".join(cmd), file=sys.stderr)
    subprocess.run(cmd, check=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", required=True, help="folder of .docx (already sorted by type, or one type)")
    ap.add_argument("--internal", default="", help="internal author whitelist, comma-separated")
    ap.add_argument("--config", help="config.json (themes/noise/stage)")
    ap.add_argument("--out", default="out")
    ap.add_argument("--name", default="corpus")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    raw = os.path.join(a.out, f"{a.name}.json")
    themes = os.path.join(a.out, f"{a.name}_themes.json")
    only = ["--only", a.internal] if a.internal else []
    run("extract.py", a.docs, "-o", raw, "--anonymize", *only)
    run("thematic.py", raw, "-o", themes, *(["--config", a.config] if a.config else []))
    run("generate_playbook.py", themes, "--mode", "skeleton", "-o",
        os.path.join(a.out, f"{a.name}_playbook.md"))
    print(f"\nDone. See {a.out}/", file=sys.stderr)

if __name__ == "__main__":
    main()
