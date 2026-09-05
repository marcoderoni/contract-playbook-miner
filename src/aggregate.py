#!/usr/bin/env python3
"""
Aggregate the extract output into a SMALL, paste-friendly summary.

    python3 aggregate.py corpus.json -o playbook_input.json

- DEDUPLICATES identical records (collapses duplicate files and copies).
- Counts, per CLAUSE, how many DISTINCT deals touch it (not raw change count).
- DROPS junk labels (over-long paragraphs mistaken for headings).
- Keeps only INTERNAL comments (your doctrine), deduplicated and capped per clause.
- Sorts by number of deals: the most frequently negotiated points first.

A "deal" = filename head before version/date/"(n)". Heuristic but robust on duplicates.
"""
import argparse, json, os, re, sys
from collections import defaultdict

JUNK_LABEL = 60          # above this = paragraph mistaken for a heading, dropped
MAX_COMMENTS = 8         # INTERNAL comments kept per clause
MAX_CLEN = 300           # comment text truncation


def deal_key(fname):
    """Deal name: strip version/date/status/(n)/extension, keep the head of the name."""
    s = os.path.splitext(fname)[0].lower()
    s = re.sub(r"\(\d+\)", " ", s)
    s = re.sub(r"\b(v\.?\d+(\.\d+)*|rev\w*|review\w*|clean|final|draft|concept|"
               r"agreed form|def|definitief|\d{1,2}[.\-]?\w{3,9}[.\-]?\d{2,4}|"
               r"\d{6,}|kpmg|nl|legal)\b", " ", s)
    s = re.sub(r"[\[\]0-9\-_]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return " ".join(s.split()[:4]) or fname.lower()


def rec_sig(r):
    return (tuple(r.get("deleted", [])), tuple(r.get("inserted", [])),
            tuple(c.get("text", "") for c in r.get("comments", [])),
            (r.get("clause_label") or r.get("clause_heading") or "").strip())


def label_of(r):
    lab = (r.get("clause_label") or r.get("clause_heading") or "").strip()
    if not lab or len(lab) > JUNK_LABEL:
        return None
    return lab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("-o", "--out", default="playbook_input.json")
    a = ap.parse_args()

    data = json.load(open(a.infile, encoding="utf-8"))

    # 1) dedup record identici (collassa file duplicati)
    seen, recs = set(), []
    for r in data:
        sig = rec_sig(r)
        if sig in seen:
            continue
        seen.add(sig)
        recs.append(r)

    # 2) aggrega per clausola
    clauses = defaultdict(lambda: {"deals": set(), "changes": 0,
                                   "internal_comments": [], "external_comments": 0})
    for r in recs:
        lab = label_of(r)
        if not lab:
            continue
        c = clauses[lab]
        c["deals"].add(deal_key(r.get("file", "")))
        if r.get("deleted") or r.get("inserted"):
            c["changes"] += 1
        for cm in r.get("comments", []):
            side = cm.get("side", "UNKNOWN")
            txt = " ".join((cm.get("text") or "").split())[:MAX_CLEN]
            if side == "INTERNAL" and txt and txt not in c["internal_comments"]:
                if len(c["internal_comments"]) < MAX_COMMENTS:
                    c["internal_comments"].append(txt)
            elif side != "INTERNAL":
                c["external_comments"] += 1

    out = []
    for lab, c in clauses.items():
        out.append({
            "clause": lab,
            "deals_touched": len(c["deals"]),
            "change_records": c["changes"],
            "internal_comments": c["internal_comments"],
            "counterparty_comment_count": c["external_comments"],
        })
    out.sort(key=lambda x: (-x["deals_touched"], -x["change_records"]))

    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"record grezzi: {len(data)}  ->  dedup: {len(recs)}  ->  clausole: {len(out)}",
          file=sys.stderr)
    print(f"\ntop clausole per DEAL distinti:", file=sys.stderr)
    for x in out[:20]:
        print(f"  {x['deals_touched']:3d} deal | {x['change_records']:4d} mod | "
              f"{len(x['internal_comments'])} commenti INTERNAL | {x['clause']}", file=sys.stderr)
    print(f"\n-> {a.out}  (paste THIS)", file=sys.stderr)


if __name__ == "__main__":
    main()
