#!/usr/bin/env python3
"""
Generate a playbook from a *_themes.json file, in one of three user-selectable modes.

    python3 generate_playbook.py themes.json                    # asks you which mode
    python3 generate_playbook.py themes.json --mode skeleton    # offline, no LLM
    python3 generate_playbook.py themes.json --mode local       # offline, local LLM (Ollama)
    python3 generate_playbook.py themes.json --mode api         # online, Anthropic API

Standard library only (urllib). No pip install.

Modes:
  skeleton  No LLM. Structures the themes into a fill-in playbook (one section per theme,
            deal-count, stage, grouped team comments). Always available, 100% offline,
            deterministic. This is the default and the fallback.
  local     Local LLM via Ollama (default http://localhost:11434). Drafts the playbook
            without leaving your machine. Requires Ollama running + a pulled model.
            Config: --endpoint, --model.
  api       Anthropic API (online, data leaves your machine). Requires internet and the
            ANTHROPIC_API_KEY environment variable. A personal-data guard runs first
            (see below). Config: --model.

ONLINE PRIVACY GUARD (api mode only):
  Before anything is sent over the network, a heuristic redaction pass masks e-mail
  addresses, @mentions, phone-like numbers and company names with legal suffixes, and
  reports how many spans were masked. You must then confirm. Heuristic redaction is NOT
  a guarantee - bare personal or client names may remain - so review is still on you.
  Use --redact/--no-redact to force it on/off, and --yes to skip the confirmation.
"""
import argparse, json, os, re, sys, urllib.request, urllib.error

CONVENTIONS = """Write a contract-review playbook SECTION for each theme, using ONLY the
positions evidenced in the provided comments/redlines. Rules:
- Default seat: the internal party is the SUPPLIER (sell-side); mark buy-side positions [buy].
- Tag every position with provenance and strength: (playbook - N deals). If a position
  rests on a single deal, mark it (playbook - provisional, 1 deal).
- Do NOT invent positions not supported by the comments. If a theme is thin, say so.
- Severity where clear: deal-breaker / important / minor.
- Give exact redline wording ("find X -> replace with Y") only where the comments support it.
- Keep client names out. Be concise and practitioner-grade."""

EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
PHONE = re.compile(r"(?<!\d)(?:\+?\d[\s().-]?){7,}\d(?!\d)")
AT_MENTION = re.compile(r"@[A-Z][\w'.-]+(?:,?\s+[A-Z][\w'.-]+){0,2}")
COMPANY = re.compile(r"([A-Z][\w&.\-]*\s+){0,3}\b(B\.?V\.?|N\.?V\.?|S\.?p\.?A\.?|S\.?r\.?l\.?|GmbH|Ltd\.?|LLC|Inc\.?|LLP)\b")


def redact(text):
    n = [0]
    def sub(pat, repl, s):
        def r(m):
            n[0] += 1; return repl
        return pat.sub(r, s)
    text = sub(EMAIL, "[EMAIL]", text)
    text = sub(PHONE, "[PHONE]", text)
    text = sub(AT_MENTION, "[NAME]", text)
    text = sub(COMPANY, "[ORG]", text)
    return text, n[0]


def load_theme_blocks(path):
    data = json.load(open(path, encoding="utf-8"))
    blocks = []
    for t in sorted(data, key=lambda x: -x.get("deals_touched", 0)):
        comments, seen = [], set()
        for ex in t.get("examples", []):
            for c in ex.get("internal", []) + ex.get("external", []):
                c = " ".join((c or "").split())
                if len(c) < 12 or c[:60] in seen:
                    continue
                seen.add(c[:60]); comments.append(c[:280])
        blocks.append({"theme": t["theme"], "deals": t.get("deals_touched", 0),
                       "stage_mix": t.get("stage_mix", {}), "comments": comments})
    return blocks


def gen_skeleton(blocks, title):
    out = [f"# {title} Playbook - SKELETON (fill in)\n",
           "> Auto-structured from mined themes. Each section lists the team's own "
           "comments\n> grouped by theme; write the standard position, rationale, "
           "fallback and redline\n> from them. Provenance tags and deal-counts are "
           "pre-filled.\n"]
    for b in blocks:
        if not b["comments"]:
            continue
        out.append(f"\n## {b['theme']}  `(playbook - {b['deals']} deals)`  "
                   f"stages: {b['stage_mix']}\n")
        out.append("**Standard position:** _[write from the comments below]_\n")
        out.append("**Fallback:** _[...]_   **Redline:** _[find -> replace]_\n")
        out.append("<details><summary>Evidence - team comments</summary>\n")
        for c in b["comments"][:20]:
            out.append(f"- {c}")
        out.append("</details>\n")
    return "\n".join(out)


def build_prompt(blocks, title):
    parts = [f"You are drafting the '{title}' section of a contract-review playbook.",
             CONVENTIONS, "\nThemes and the team's evidenced comments:\n"]
    for b in blocks:
        if not b["comments"]:
            continue
        parts.append(f"\n### {b['theme']} (deals_touched={b['deals']}, stages={b['stage_mix']})")
        for c in b["comments"][:25]:
            parts.append(f"- {c}")
    parts.append("\nNow write the playbook in Markdown, one section per theme, "
                 "with provenance tags as specified.")
    return "\n".join(parts)


def gen_local(blocks, title, endpoint, model):
    prompt = build_prompt(blocks, title)
    body = json.dumps({"model": model, "prompt": prompt, "stream": False}).encode()
    req = urllib.request.Request(endpoint.rstrip("/") + "/api/generate",
                                 data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.loads(r.read())["response"]
    except (urllib.error.URLError, OSError) as e:
        sys.exit(f"[local] cannot reach Ollama at {endpoint}: {e}\n"
                 f"Start Ollama and pull the model (e.g. `ollama pull {model}`), "
                 f"or use --mode skeleton.")


def gen_api(blocks, title, model, do_redact, assume_yes):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        sys.exit("[api] ANTHROPIC_API_KEY is not set. Set it, or use --mode skeleton (offline).")
    prompt = build_prompt(blocks, title)
    if do_redact:
        prompt, masked = redact(prompt)
        print(f"[api] privacy guard: masked {masked} span(s) "
              f"(emails/@mentions/phones/orgs).", file=sys.stderr)
    print("[api] This sends the (redacted) theme text to Anthropic over the network.\n"
          "      Heuristic redaction is not a guarantee - bare personal/client names may "
          "remain.", file=sys.stderr)
    if not assume_yes:
        try:
            if input("      Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
                sys.exit("Aborted. Use --mode skeleton to stay offline.")
        except EOFError:
            sys.exit("No confirmation (non-interactive). Re-run with --yes, or use --mode skeleton.")
    body = json.dumps({"model": model, "max_tokens": 4096,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=body,
        headers={"content-type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.loads(r.read())
            return "".join(p.get("text", "") for p in data.get("content", []))
    except urllib.error.HTTPError as e:
        sys.exit(f"[api] HTTP {e.code}: {e.read().decode(errors='ignore')[:300]}")
    except (urllib.error.URLError, OSError) as e:
        sys.exit(f"[api] network unavailable: {e}. Use --mode skeleton to work offline.")


def choose_mode():
    print("Choose playbook generation mode:", file=sys.stderr)
    print("  1) skeleton  - offline, no LLM (default)", file=sys.stderr)
    print("  2) local     - offline, local LLM via Ollama", file=sys.stderr)
    print("  3) api       - online, Anthropic API (data leaves your machine)", file=sys.stderr)
    try:
        c = input("Mode [1/2/3, default 1]: ").strip()
    except EOFError:
        return "skeleton"
    return {"2": "local", "3": "api"}.get(c, "skeleton")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("themes", help="a *_themes.json file")
    ap.add_argument("--mode", choices=["skeleton", "local", "api"],
                    help="if omitted, you will be asked interactively")
    ap.add_argument("-o", "--out")
    ap.add_argument("--title")
    ap.add_argument("--endpoint", default="http://localhost:11434", help="Ollama endpoint (local mode)")
    ap.add_argument("--model", help="model: default 'llama3.1' (local) / 'claude-sonnet-4-6' (api)")
    ap.add_argument("--redact", dest="redact", action="store_true", default=None,
                    help="force the online privacy guard on (default: on for api mode)")
    ap.add_argument("--no-redact", dest="redact", action="store_false",
                    help="disable the online privacy guard (not recommended)")
    ap.add_argument("--yes", action="store_true", help="skip the api-mode confirmation prompt")
    a = ap.parse_args()

    mode = a.mode or choose_mode()
    title = a.title or os.path.splitext(os.path.basename(a.themes))[0].replace("_themes", "")
    blocks = load_theme_blocks(a.themes)
    if not any(b["comments"] for b in blocks):
        sys.exit("No team comments in the themes: nothing to synthesise.")

    if mode == "skeleton":
        text = gen_skeleton(blocks, title)
    elif mode == "local":
        text = gen_local(blocks, title, a.endpoint, a.model or "llama3.1")
    else:
        do_redact = True if a.redact is None else a.redact
        text = gen_api(blocks, title, a.model or "claude-sonnet-4-6", do_redact, a.yes)

    out = a.out or f"{title}_playbook.md"
    open(out, "w", encoding="utf-8").write(text)
    print(f"[{mode}] -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
