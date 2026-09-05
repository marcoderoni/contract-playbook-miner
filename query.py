#!/usr/bin/env python3
"""
Search engine over extracted redlines + comments: find what was discussed/agreed on ANY
topic, even if it is not one of the main themes.

    python3 query.py corpus.json "audit"                     # OR: any of the terms
    python3 query.py corpus.json "sub-processor" "consent" --all   # AND: all terms
    python3 query.py Sorted "benchmark" -o hits.json          # search every *.json in a folder
    python3 query.py corpus.json "liability" --internal-only  # only where an INTERNAL author commented

Searches: clause label, paragraph text, deleted/inserted text, comments.
Anonymised output (DEAL_n, @mentions removed). Review residual client names before sharing.
"""
import argparse, glob, json, os, re, sys
from collections import defaultdict

MAX_HITS = 120
MAX_TXT = 400
AT_MENTION = re.compile(r"@[A-Z][\w'’.-]+(?:,?\s+[A-Z][\w'’.-]+){0,2}")

STAGE = [("final", ["final", "consolidated", "executed", "signed", "getekend"]),
         ("review", ["review", "comments", "redline", "markup", "mark up", "rev "]),
         ("template", ["template", "agreed form", "model"]),
         ("opening", ["draft", "concept"])]


def stage_of(f):
    s = f.lower()
    for lab, kws in STAGE:
        if any(k in s for k in kws):
            return lab
    return "unknown"


def deal_key(f):
    s = os.path.splitext(f)[0].lower()
    s = re.sub(r"\(\d+\)", " ", s)
    s = re.sub(r"\b(v\.?\d+(\.\d+)*|rev\w*|review\w*|clean|final|draft|concept|"
               r"consolidated|agreed form|def|definitief|template|kpmg|nl|legal|"
               r"\d{1,2}[.\-]?\w{3,9}[.\-]?\d{2,4}|\d{6,})\b", " ", s)
    s = re.sub(r"[\[\]0-9\-_]+", " ", s)
    return " ".join(s.split()[:4]).strip()


def scrub(t):
    return " ".join(AT_MENTION.sub("[NAME]", (t or "")).split())[:MAX_TXT]


def load(paths):
    files = []
    for p in paths:
        if os.path.isdir(p):
            files += glob.glob(os.path.join(p, "**", "*.json"), recursive=True)
        else:
            files += glob.glob(p)
    recs = []
    for f in sorted(set(files)):
        try:
            data = json.load(open(f, encoding="utf-8"))
            if isinstance(data, list):
                recs += data
        except Exception as e:
            print(f"[skip] {f}: {e}", file=sys.stderr)
    return recs


def hay(r):
    return " ".join([
        r.get("clause_label") or "", r.get("clause_heading") or "",
        r.get("paragraph_text") or "",
        " ".join(r.get("deleted", [])), " ".join(r.get("inserted", [])),
        " ".join(c.get("text", "") for c in r.get("comments", [])),
    ]).lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="+", help="a .json file, glob, or folder; THEN the search terms")
    ap.add_argument("--all", action="store_true", help="require ALL terms (AND)")
    ap.add_argument("--internal-only", action="store_true", help="only records with an INTERNAL comment")
    ap.add_argument("-o", "--out", default="query_hits.json")
    a = ap.parse_args()

    # separate sources (existing files / .json globs) from search terms
    srcs = [s for s in a.source if os.path.isdir(s) or glob.glob(s)]
    terms = [s.lower() for s in a.source if s not in srcs]
    if not srcs or not terms:
        ap.error("usage: query.py <.json file/folder> <term> [term...] [--all]")

    recs = load(srcs)
    deal_ids, hits, seen = {}, [], set()
    per_deal = defaultdict(int)

    for r in recs:
        h = hay(r)
        ok = all(t in h for t in terms) if a.all else any(t in h for t in terms)
        if not ok:
            continue
        kpmg = [scrub(c["text"]) for c in r.get("comments", []) if c.get("side") == "INTERNAL" and c.get("text")]
        cp = [scrub(c["text"]) for c in r.get("comments", []) if c.get("side") != "INTERNAL" and c.get("text")]
        if a.internal_only and not kpmg:
            continue
        dk = deal_key(r.get("file", ""))
        deal_ids.setdefault(dk, f"DEAL_{len(deal_ids)+1}")
        ex = {
            "deal": deal_ids[dk],
            "stage": stage_of(r.get("file", "")),
            "clause": (r.get("clause_label") or r.get("clause_heading") or "")[:80],
            "deleted": [scrub(x) for x in r.get("deleted", []) if len(x.strip()) > 2][:3],
            "inserted": [scrub(x) for x in r.get("inserted", []) if len(x.strip()) > 2][:3],
            "internal": [c for c in kpmg if c][:4],
            "external": [c for c in cp if c][:3],
        }
        sig = json.dumps(ex, ensure_ascii=False, sort_keys=True)
        if sig in seen:
            continue
        seen.add(sig)
        per_deal[ex["deal"]] += 1
        if len(hits) < MAX_HITS:
            hits.append(ex)

    json.dump(hits, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    mode = "AND" if a.all else "OR"
    print(f"termini {terms} [{mode}] -> {len(hits)} hit in {len(per_deal)} deal (su {len(recs)} record)",
          file=sys.stderr)
    for d, n in sorted(per_deal.items(), key=lambda x: -x[1]):
        print(f"  {n:3d}  {d}", file=sys.stderr)
    print(f"\n-> {a.out}  (review residual client names before sharing)", file=sys.stderr)


if __name__ == "__main__":
    main()
