---
name: contract-review
description: >
  Review or mark up a contract against a mined playbook. Use when the user uploads or
  pastes a contract and asks to review it, flag issues, redline it, or compare it to
  standard positions. [Customise this description for your practice, types, and seat.]
---

# Contract Review (template)

Fill this in for your practice. The workflow below is the recommended structure.

## When this triggers
Any request to review / mark up / check / redline a contract.

## Review workflow
1. IDENTIFY TYPE -> load the matching file in `playbooks/`.
2. IDENTIFY SEAT (are you the supplier or the customer?) — positions may invert.
3. Load `cross-cutting.md` + the type playbook.
4. Flag every deviation as an issue (see output format).
5. State what you did NOT check (no playbook position) so gaps are visible.

## Output format
[Choose: prose memo / issues table / two-layer summary+detail. Keep a severity
hierarchy: deal-breaker / important / minor. Give exact "find X -> replace with Y"
redlines. Keep verbatim contract text separate from interpretation.]

## Provenance tagging (recommended)
Tag each position: `(playbook - N deals)` for mined positions, `(model - not in playbook)`
for the assistant's own reasoning, so the user sees what rests on real precedent.

## Gaps
List the topics your corpus does not yet cover (e.g. new regulations) so the assistant
flags rather than invents.
