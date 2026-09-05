#!/usr/bin/env python3
"""
Classify contracts by TYPE, in two steps.

STEP 1 - profile (no client names leave the machine):
    python3 classify.py "/path/Contracts" --profile -o types.txt
  Counts recurring words in filenames and drops rare ones (likely proper names).
  Paste types.txt to review; the rest (client names) stays local.

STEP 2 - sort, using a category->keywords rules file:
    python3 classify.py "/path/Contracts" --sort rules.json --dest "/path/Sorted"
  Copies each file into its category subfolder. _UNSORTED = no rule matched;
  _MULTI = several categories matched.

Standard library only. Copies by default (originals untouched). Use --move to move.
"""
import argparse, glob, json, os, re, shutil, sys
from collections import Counter

# noise to ignore when profiling types: versions, statuses, months
NOISE = {
    "def", "definitief", "final", "clean", "draft", "concept", "review", "reviewed",
    "kpmg", "nl", "legal", "signed", "getekend", "ondertekend", "copy", "kopie",
    "v", "vs", "version", "versie", "the", "and", "van", "de", "het", "een", "voor",
    "met", "en", "of", "to", "for", "with", "agreement",  # 'agreement' troppo generico da solo
    "overeenkomst",  # idem: quasi ovunque, non discrimina
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec",
    "januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus",
    "september", "oktober", "november", "december", "final",
}
DATELIKE = re.compile(r"^\d{1,8}$|^\d{4}[-_.]\d{2}[-_.]\d{2}$|^v?\d+(\.\d+)*$")


def tokens(stem):
    parts = re.split(r"[\s_\-.,()\[\]]+", stem.lower())
    out = []
    for p in parts:
        p = p.strip()
        if not p or DATELIKE.match(p) or p in NOISE or len(p) <= 1:
            continue
        out.append(p)
    return out


def iter_docx(root):
    if os.path.isdir(root):
        for p in glob.glob(os.path.join(root, "**", "*.docx"), recursive=True):
            if not os.path.basename(p).startswith("~$"):
                yield p
    else:
        for p in glob.glob(root):
            yield p


def profile(root, out):
    uni, bi, files = Counter(), Counter(), 0
    for path in iter_docx(root):
        files += 1
        toks = tokens(os.path.splitext(os.path.basename(path))[0])
        seen = set(toks)
        uni.update(seen)
        bi.update({f"{a} {b}" for a, b in zip(toks, toks[1:])})
    lines = []
    lines.append(f"# {files} file profilati\n")
    lines.append("# RECURRING WORDS (word -> in how many files). Below 2 = likely proper name, omitted.\n")
    for w, c in uni.most_common():
        if c >= 2:
            lines.append(f"{c:5d}  {w}")
    lines.append("\n# RECURRING PAIRS (useful for two-word types):\n")
    for w, c in bi.most_common():
        if c >= 2:
            lines.append(f"{c:5d}  {w}")
    txt = "\n".join(lines)
    with open(out, "w", encoding="utf-8") as f:
        f.write(txt)
    print(txt[:2000], file=sys.stderr)
    print(f"\n-> {out}  ({files} file). Paste THIS to review; not the filenames.", file=sys.stderr)


def sort_files(root, rules_path, dest, move=False):
    with open(rules_path, encoding="utf-8") as f:
        rules = json.load(f)  # {"Categoria": ["kw1","kw2", ...], ...}
    compiled = {cat: [k.lower() for k in kws] for cat, kws in rules.items()}
    counts = Counter()
    for path in iter_docx(root):
        stem = os.path.splitext(os.path.basename(path))[0].lower()
        hits = [cat for cat, kws in compiled.items() if any(k in stem for k in kws)]
        if not hits:
            target = "_UNSORTED"
        elif len(set(hits)) > 1:
            target = "_MULTI__" + "+".join(sorted(set(hits)))
        else:
            target = hits[0]
        folder = os.path.join(dest, target)
        os.makedirs(folder, exist_ok=True)
        dst = os.path.join(folder, os.path.basename(path))
        (shutil.move if move else shutil.copy2)(path, dst)
        counts[target] += 1
    print("\nsort result:", file=sys.stderr)
    for cat, c in counts.most_common():
        print(f"  {c:4d}  {cat}", file=sys.stderr)
    print(f"\nCheck _UNSORTED and _MULTI by hand before proceeding.", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", help="folder (or glob) of contracts")
    ap.add_argument("--profile", action="store_true", help="step 1: count type keywords")
    ap.add_argument("--sort", metavar="RULES.json", help="step 2: sort into folders per rules")
    ap.add_argument("--dest", help="destination folder for --sort")
    ap.add_argument("--move", action="store_true", help="move instead of copy")
    ap.add_argument("-o", "--out", default="types.txt")
    a = ap.parse_args()
    if a.profile:
        profile(a.root, a.out)
    elif a.sort:
        if not a.dest:
            ap.error("--sort requires --dest")
        sort_files(a.root, a.sort, a.dest, a.move)
    else:
        ap.error("choose --profile or --sort")


if __name__ == "__main__":
    main()
