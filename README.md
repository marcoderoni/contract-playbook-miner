# redline-miner

![Python](https://img.shields.io/badge/python-3.9%2B-blue) ![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen) ![Offline](https://img.shields.io/badge/runs-offline-success) ![License](https://img.shields.io/badge/license-MIT-lightgrey)

Mine your own past contract redlines and comments into a reusable **review playbook** —
and, optionally, a Claude/LLM **skill** that applies it to new contracts.

Point it at a folder of reviewed `.docx` files. It extracts every tracked change and
comment, groups them by theme, keeps only your team's positions, and produces a
structured playbook you can refine. **Runs fully offline. Standard library only. No data
leaves your machine.**

> **Privacy first.** This repo ships **no contract data** and the `.gitignore` blocks
> `*.docx`, `*.json` (except examples), generated playbooks and author lists from ever
> being committed. Keep it that way.

## Why

Your negotiation doctrine already exists — scattered across hundreds of reviewed
contracts as tracked changes and margin comments. This turns that latent knowledge into
an explicit, searchable playbook, evidenced by how many deals each position appears in.

## Requirements

Python 3.9+. Nothing else. (Optional: a local LLM runtime such as Ollama for
`--mode local`, or an Anthropic API key for `--mode api`.)

## Quick start (offline, with synthetic test data)

```bash
python3 src/make_fixtures.py tests/fixtures
python3 run.py --docs tests/fixtures --internal "Jane Doe,John Smith" --name demo --out out
# -> out/demo.json, out/demo_themes.json, out/demo_playbook.md
```

## Pipeline

| Step | Script | What it does |
|------|--------|--------------|
| 1. Classify | `src/classify.py` | Profile filename types, sort `.docx` into per-type folders |
| 2. Extract | `src/extract.py` | Pull tracked changes + comments to JSON; tag author role (INTERNAL/EXTERNAL); `--only` whitelist; `--anonymize` |
| 3. Thematise | `src/thematic.py` | Group by theme, tag stage, filter noise, anonymise deals |
| 4. Aggregate | `src/aggregate.py` | Dedup, count by distinct deal, drop junk labels |
| 5. Query | `src/query.py` | Search any topic across all redlines + comments |
| 6. Generate | `src/generate_playbook.py` | Turn themes into a playbook (3 modes below) |

Customise types in `examples/rules.example.json` and themes/noise in
`config.example.json` (copy to `config.json`).

## Playbook generation — you choose the mode

| Mode | Command | Network | Needs |
|------|---------|---------|-------|
| **skeleton** (default) | `--mode skeleton` | **offline** | nothing — structures themes into a fill-in playbook |
| **local** | `--mode local` | **offline** | a local LLM (Ollama) at `localhost:11434` |
| **api** | `--mode api` | online | internet + `ANTHROPIC_API_KEY` |

```bash
python3 src/generate_playbook.py out/demo_themes.json --mode skeleton
python3 src/generate_playbook.py out/demo_themes.json --mode local --model llama3.1
ANTHROPIC_API_KEY=... python3 src/generate_playbook.py out/demo_themes.json --mode api
```

**Honest limit:** the extraction/analysis is fully deterministic and offline. Writing
polished playbook prose from the evidence needs a model — `skeleton` gives you the
structured evidence to write from by hand; `local`/`api` draft it for you. Nothing forces
you online.

## Building a skill

`skill_template/` contains an empty `SKILL.md`, `cross-cutting.md` and a playbook
template. Fill them with the playbooks you generate; the result is a private skill that
reviews new contracts against your positions. Keep filled playbooks out of git
(`.gitignore` already excludes `playbooks/`).

## Anonymisation caveat

`--anonymize` masks company names with legal suffixes (BV, Ltd, GmbH, …). It does **not**
catch personal names or figures inside clause text. Always eyeball generated output
before sharing it outside your team.

## License

MIT. See `LICENSE`.
