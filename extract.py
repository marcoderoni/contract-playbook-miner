#!/usr/bin/env python3
"""
Extract tracked changes + comments from .docx -> JSON (one record per changed paragraph).

--only "name1,name2,...": WHITELIST. Keep ONLY comments and tracked changes by the listed
authors (your internal team), dropping everyone else. A record with no team content after
filtering is dropped. Ideal for mining your own review doctrine.

    python3 extract.py FOLDER --list-authors
    python3 extract.py FOLDER -o out.json --anonymize --only "Jane Doe,John Smith"

Standard library only.
"""
import argparse, glob, json, os, re, sys, zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _text_of(el, tags=("t", "delText")):
    want = {W + t for t in tags}
    return "".join(n.text or "" for n in el.iter() if n.tag in want)


def _toks(s):
    return set(re.findall(r"[a-zà-ÿ0-9]+", (s or "").lower()))


def matches(name, whitelist):
    """whitelist = lista di set di token; match se TUTTI i token di una voce
    sono nel nome autore (ordine/punteggiatura irrilevanti)."""
    if not whitelist:
        return True
    nt = _toks(name)
    return any(entry and entry <= nt for entry in whitelist)


def load_comments(z):
    out = {}
    if "word/comments.xml" not in z.namelist():
        return out
    root = ET.fromstring(z.read("word/comments.xml"))
    for c in root.iter(W + "comment"):
        out[c.get(W + "id")] = {
            "author": c.get(W + "author"),
            "date": c.get(W + "date"),
            "text": " ".join(_text_of(c).split()),
        }
    return out


STOP = {"of","and","the","to","for","in","or","a","an","by","with","on","from"}
LEADIN = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?([A-Z0-9][^.:;\u2022]{1,60}?)\s*[.:]\s")


def leadin_of(text):
    m = LEADIN.match(text or "")
    if not m:
        return None
    label = m.group(1).strip()
    words = label.split()
    if not 1 <= len(words) <= 8:
        return None
    core = [w for w in words if w.lower().strip("(),") not in STOP]
    if not core or not all(w[0].isupper() or w[0].isdigit() for w in core):
        return None
    return label


def heading_of(p):
    st = p.find(f"{W}pPr/{W}pStyle")
    val = st.get(W + "val") if st is not None else None
    return val if val and val.lower().startswith(("heading", "titolo", "kop")) else None


def parse_docx(path, comments_only=False, only=None):
    with zipfile.ZipFile(path) as z:
        comments = load_comments(z)
        root = ET.fromstring(z.read("word/document.xml"))

    records, current_heading, open_comments = [], None, []
    for p in root.iter(W + "p"):
        ptext = " ".join(_text_of(p).split())
        if heading_of(p):
            current_heading = ptext or current_heading
        label = leadin_of(ptext)
        if label:
            current_heading = label

        ins, dele = [], []      # lists of (text, author)
        for node in p.iter():
            if node.tag == W + "ins":
                ins.append((_text_of(node, ("t",)), node.get(W + "author")))
            elif node.tag == W + "del":
                dele.append((_text_of(node, ("delText",)), node.get(W + "author")))
            elif node.tag == W + "commentRangeStart":
                open_comments.append(node.get(W + "id"))

        cmt_ids = [i for i in open_comments if i in comments]
        for node in p.iter(W + "commentRangeEnd"):
            cid = node.get(W + "id")
            if cid in open_comments:
                open_comments.remove(cid)

        cmts = [comments[i] for i in cmt_ids]

        # --- whitelist filter: keep only team content ---
        if only:
            ins = [(t, au) for (t, au) in ins if matches(au, only)]
            dele = [(t, au) for (t, au) in dele if matches(au, only)]
            cmts = [c for c in cmts if matches(c.get("author"), only)]

        if not (ins or dele or cmts):
            continue
        if comments_only and not cmts:
            continue

        authors = sorted({au for (_, au) in ins + dele if au} |
                         {c["author"] for c in cmts if c.get("author")})
        records.append({
            "file": os.path.basename(path),
            "clause_heading": current_heading,
            "clause_label": label,
            "type": ("both" if (ins or dele) and cmts
                     else "redline_only" if (ins or dele) else "comment_only"),
            "paragraph_text": ptext,
            "deleted": [" ".join(t.split()) for (t, _) in dele if t.strip()],
            "inserted": [" ".join(t.split()) for (t, _) in ins if t.strip()],
            "authors": authors,
            "comments": cmts,
        })
    return records


NAME_HINTS = re.compile(
    r"\b(B\.?V\.?|N\.?V\.?|S\.?p\.?A\.?|S\.?r\.?l\.?|GmbH|Ltd\.?|LLC|Inc\.?)\b")


def role_of(name, internal):
    if not name:
        return "UNKNOWN"
    return "INTERNAL" if matches(name, internal) else "EXTERNAL"


def anonymize(rec, mapping, internal, people):
    def scrub(s):
        if not s:
            return s
        def repl(m):
            key = m.group(0)
            mapping.setdefault(key, f"PARTY_{len(mapping)+1}")
            return mapping[key]
        return re.sub(r"([A-Z][\w&.\-]*\s+){0,3}" + NAME_HINTS.pattern, repl, s)

    def pseudo(name):
        r = role_of(name, internal)
        people.setdefault(name, f"{r}_{sum(1 for v in people.values() if v.startswith(r)) + 1}")
        return people[name]

    for k in ("paragraph_text", "clause_heading"):
        rec[k] = scrub(rec.get(k))
    rec["deleted"] = [scrub(x) for x in rec["deleted"]]
    rec["inserted"] = [scrub(x) for x in rec["inserted"]]
    for c in rec["comments"]:
        c["text"] = scrub(c["text"])
        c["side"] = role_of(c["author"], internal)
        c["author"] = pseudo(c["author"])
    rec["sides"] = sorted({role_of(a, internal) for a in rec["authors"]})
    rec["authors"] = [pseudo(a) for a in rec["authors"]]
    return rec


def list_authors(paths):
    from collections import defaultdict
    tally = defaultdict(lambda: [0, set()])
    for path in paths:
        try:
            recs = parse_docx(path)
        except Exception as e:
            print(f"[skip] {path}: {e}", file=sys.stderr); continue
        fname = os.path.basename(path)
        for r in recs:
            for n in set(r["authors"]) | {c["author"] for c in r["comments"] if c.get("author")}:
                if n:
                    tally[n][0] += 1
                    tally[n][1].add(fname)
    rows = sorted(tally.items(), key=lambda kv: (-len(kv[1][1]), -kv[1][0]))
    print(f"\n{'mod':>5}  {'file':>4}  autore", file=sys.stderr)
    print("  " + "-" * 44, file=sys.stderr)
    for name, (cnt, files) in rows:
        flag = "  <- 1 solo file" if len(files) == 1 else ""
        print(f"{cnt:>5}  {len(files):>4}  {name}{flag}", file=sys.stderr)
    print(f"\n{len(rows)} distinct authors across {len(paths)} files.", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("-o", "--out", default="dataset.json")
    ap.add_argument("--anonymize", action="store_true")
    ap.add_argument("--comments-only", action="store_true")
    ap.add_argument("--list-authors", action="store_true")
    ap.add_argument("--internal", default="", help="internal authors (labels INTERNAL vs EXTERNAL)")
    ap.add_argument("--only", default="",
                    help="WHITELIST: keep ONLY comments/redlines by these authors (your internal team)")
    a = ap.parse_args()

    paths = []
    for i in a.inputs:
        if os.path.isdir(i):
            paths += glob.glob(os.path.join(i, "**", "*.docx"), recursive=True)
        else:
            paths += glob.glob(i)
    paths = [p for p in sorted(set(paths)) if not os.path.basename(p).startswith("~$")]

    if a.list_authors:
        list_authors(paths)
        return

    only = [_toks(x) for x in a.only.split(",") if _toks(x)]
    # con --only, chi resta e' per definizione team -> usalo anche come 'internal'
    internal = [_toks(x) for x in a.internal.split(",") if _toks(x)] or only

    all_recs, mapping, people, kept_files = [], {}, {}, 0
    for p in paths:
        try:
            recs = parse_docx(p, a.comments_only, only)
        except Exception as e:
            print(f"[skip] {p}: {e}", file=sys.stderr); continue
        if recs:
            kept_files += 1
        if a.anonymize:
            recs = [anonymize(r, mapping, internal, people) for r in recs]
        all_recs += recs

    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(all_recs, f, ensure_ascii=False, indent=1)

    from collections import Counter
    if a.only:
        print(f"whitelist active: {len(only)} authors kept", file=sys.stderr)
    if a.anonymize:
        print("authors:", dict(Counter(v.rsplit("_",1)[0] for v in people.values())), file=sys.stderr)
    print("tipo:", dict(Counter(r["type"] for r in all_recs)), file=sys.stderr)
    print(f"\n{len(all_recs)} record da {kept_files} file (con contenuto team) -> {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
