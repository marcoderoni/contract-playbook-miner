#!/usr/bin/env python3
"""
Thematic aggregator - turns the extract output (even over thousands of files) into a
small, paste-friendly per-theme corpus for playbook synthesis: broad (by theme) and
deep (fallbacks per theme).

    python3 thematic.py corpus.json -o corpus_themes.json

What it does automatically (no file to open by hand):
- assigns each record to one or more THEMES;
- infers the STAGE from the filename (opening / review / final / template);
- anonymises the DEAL (DEAL_1, DEAL_2, ...) and strips @mentions from comments;
- dedups and caps examples per theme (so it stays paste-friendly);
- separates INTERNAL positions from EXTERNAL pressure (= where you typically concede).

Override THEMES/NOISE/STAGE via --config <json>.
"""
import argparse, json, os, re, sys
from collections import defaultdict

MAX_PER_THEME = 60      # examples kept per theme
MAX_TXT = 400           # text truncation

# --- themes: keyword -> match on clause_label + text + comment (lowercased) ---
THEMES = {
    "liability":         ["liability", "aansprakelijk", "limitation of liability", "cap on", "indirect", "consequential", "gevolgschade"],
    "indemnity":         ["indemnif", "indemnit", "vrijwaring", "hold harmless"],
    "ip_ownership":      ["intellectual property", "ip right", "work product", "ownership", "eigendom", "auteursrecht", "proprietary"],
    "licence":           ["licence", "license", "licentie", "right to use", "gebruiksrecht"],
    "data_privacy":      ["data protection", "data processing", "dpa", "verwerker", "personal data", "persoonsgegev", "gdpr", "avg", "sub-processor", "subprocessor"],
    "confidentiality":   ["confidential", "geheimhouding", "vertrouwelijk", "non-disclosure", "nda"],
    "termination":       ["termination", "terminate", "opzegg", "beeindig", "looptijd", "term and termination"],
    "warranty":          ["warrant", "garantie", "fit for purpose", "conformity", "representation"],
    "force_majeure":     ["force majeure", "overmacht"],
    "service_levels":    ["service level", "sla", "kpi", "uptime", "availability", "support hour", "incident", "response time"],
    "fees_payment":      ["fees", "payment", "betaling", "price", "prijs", "vergoeding", "invoice", "factuur", "indexation", "indexering", "rate card", "surcharge"],
    "insurance":         ["insurance", "verzekering"],
    "assignment":        ["assignment", "overdracht", "novation", "assign this"],
    "governing_law":     ["governing law", "jurisdiction", "toepasselijk recht", "rechtsmacht", "arbitration", "arbitrage", "geschil", "dispute resolution"],
    "subcontracting":    ["subcontract", "onderaannem", "onderaanneming", "sub-contractor"],
    "acceptance_change": ["acceptance", "delivery", "oplevering", "aanvaarding", "change control", "change request", "wijziging", "change note"],
}

STAGE = [
    ("final",    ["final", "consolidated", "executed", "executable", "signed", "getekend", "ondertekend"]),
    ("review",   ["review", "comments", "redline", "mark up", "markup", "revcall", "rev "]),
    ("template", ["template", "agreed form", "model"]),
    ("opening",  ["draft", "concept", "v0", "v1"]),
]

AT_MENTION = re.compile(r"@[A-Z][\w'’.-]+(?:,?\s+[A-Z][\w'’.-]+){0,2}")

# noise comments (matched lowercased): coordination/status/boilerplate
NOISE_COMMENTS = [
    "amended to reflect our agreement", "changes from the current finance msa",
    "it was agreed as a point of principle", "mg regards secondment",
    "our dp lawyer has commented", "for ease of read", "note - further amended",
    "note – further amended", "further amended for sense",
]
NOISE_EXACT = {
    "updated", "reinserted", "reinserted.", "removed", "removed.", "added", "added.",
    "adjusted", "adjusted.", "confirmed", "confirmed.", "open", "open.", "not applicable",
    "not applicable.", "not applicable. removed", "not applicable. removed.",
    "wendy to confirm", "wendy to confirm.", "yes.", "yes", "[name]", "[name] [name]",
    "in msa.", "correct", "correct.",
}
POSITION_HINT = re.compile(
    r"(not acceptable|not approved|cannot? (accept|agree)|we can accept|reject|delete|"
    r"remove|refer to|not applicable|please (confirm|explain|elaborate|reconsider|clarify)|"
    r"is this applicable|no limitation|must|should|prevail|fit for|too (wide|long|vague)|"
    r"strike|dutch law|new sow|written approval|exit|cure|refund|days|weeks|month|%|"
    r"blijft eigendom|niet accept|max\.|beperking)", re.I)


def _clean_comment(t):
    t = " ".join((t or "").split())
    if not t:
        return None
    low = re.sub(r"[\s]+", " ", t.lower()).strip()
    low_np = low.rstrip(".?! ")
    if low_np in NOISE_EXACT or low in NOISE_EXACT:
        return None
    if any(n in low for n in NOISE_COMMENTS):
        return None
    # solo @menzioni / [NAME] senza sostanza
    stripped = t.replace("[NAME]", "").strip(" :?-–,")
    if len(stripped) < 4:
        return None
    return t[:MAX_TXT]


def _clean_frag(x):
    x = " ".join((x or "").split())
    # drop tiny fragments: <=2 chars, punctuation only, or a single very short word
    if len(x) <= 2:
        return None
    if not re.search(r"[A-Za-zÀ-ÿ]{3,}", x):
        return None
    return x[:MAX_TXT]


def stage_of(fname):
    s = fname.lower()
    for label, kws in STAGE:
        if any(k in s for k in kws):
            return label
    return "unknown"


def deal_key(fname):
    s = os.path.splitext(fname)[0].lower()
    s = re.sub(r"\(\d+\)", " ", s)
    s = re.sub(r"\b(v\.?\d+(\.\d+)*|rev\w*|review\w*|clean|final|draft|concept|"
               r"consolidated|agreed form|def|definitief|template|kpmg|nl|legal|"
               r"\d{1,2}[.\-]?\w{3,9}[.\-]?\d{2,4}|\d{6,})\b", " ", s)
    s = re.sub(r"[\[\]0-9\-_]+", " ", s)
    return " ".join(s.split()[:4]).strip()


def scrub(t):
    if not t:
        return t
    return " ".join(AT_MENTION.sub("[NAME]", t).split())[:MAX_TXT]


def themes_of(r):
    hay = " ".join([
        (r.get("clause_label") or ""), (r.get("clause_heading") or ""),
        (r.get("paragraph_text") or ""),
        " ".join(r.get("deleted", [])), " ".join(r.get("inserted", [])),
        " ".join(c.get("text", "") for c in r.get("comments", [])),
    ]).lower()
    return [t for t, kws in THEMES.items() if any(k in hay for k in kws)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("infile")
    ap.add_argument("-o", "--out", default="themes.json")
    ap.add_argument("--config", help="optional JSON to override THEMES/NOISE/STAGE")
    a = ap.parse_args()
    if getattr(a, "config", None):
        cfg = json.load(open(a.config, encoding="utf-8"))
        globals().update({k: cfg[k] for k in ("THEMES", "NOISE_COMMENTS", "NOISE_EXACT", "STAGE") if k in cfg})
    data = json.load(open(a.infile, encoding="utf-8"))

    deal_ids, buckets = {}, defaultdict(lambda: {"deals": set(), "stages": defaultdict(int), "ex": [], "seen": set()})

    for r in data:
        dk = deal_key(r.get("file", ""))
        if dk not in deal_ids:
            deal_ids[dk] = f"DEAL_{len(deal_ids) + 1}"
        did = deal_ids[dk]
        st = stage_of(r.get("file", ""))
        for th in themes_of(r):
            b = buckets[th]
            b["deals"].add(did)
            b["stages"][st] += 1
            kpmg = [_clean_comment(scrub(c["text"])) for c in r.get("comments", []) if c.get("side") == "INTERNAL" and c.get("text")]
            cp = [_clean_comment(scrub(c["text"])) for c in r.get("comments", []) if c.get("side") != "INTERNAL" and c.get("text")]
            kpmg = [c for c in kpmg if c]
            cp = [c for c in cp if c]
            dele = [f for f in (_clean_frag(scrub(x)) for x in r.get("deleted", [])) if f][:3]
            ins = [f for f in (_clean_frag(scrub(x)) for x in r.get("inserted", [])) if f][:3]
            # keep the example only if SUBSTANCE remains: a comment stating a position,
            # or a non-trivial redline
            has_position = any(POSITION_HINT.search(c) for c in kpmg + cp)
            has_redline = bool(dele or ins)
            if not (has_position or (has_redline and (kpmg or cp))):
                # allow a pure redline only if long enough (a real substantive change)
                if not (has_redline and any(len(f) > 25 for f in dele + ins)):
                    continue
            ex = {
                "stage": st,
                "deleted": dele,
                "inserted": ins,
                "internal": kpmg[:4],
                "external": cp[:2],
            }
            sig = json.dumps(ex, ensure_ascii=False, sort_keys=True)
            if sig in b["seen"]:
                continue
            b["seen"].add(sig)
            if len(b["ex"]) < MAX_PER_THEME:
                b["ex"].append(ex)

    out = []
    for th, b in buckets.items():
        out.append({
            "theme": th,
            "deals_touched": len(b["deals"]),
            "stage_mix": dict(b["stages"]),
            "examples": b["ex"],
        })
    out.sort(key=lambda x: -x["deals_touched"])
    json.dump(out, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"deal distinti: {len(deal_ids)}", file=sys.stderr)
    print(f"\ntheme                | deal | examples", file=sys.stderr)
    print("  " + "-" * 44, file=sys.stderr)
    for x in out:
        print(f"  {x['theme']:18} | {x['deals_touched']:4d} | {len(x['examples'])}", file=sys.stderr)
    print(f"\n-> {a.out}  (paste THIS; eyeball residual [NAME] spans)", file=sys.stderr)


if __name__ == "__main__":
    main()
