# Test Plan — gmj-template

This file verifies the `gmj-template` flow for a human operator running it directly.

## Setup & Preconditions

No preconditions — this flow has no setup requirements beyond the repo's standard `pip install` step.

## Test 1 — gmj-template

**Proves:** TEMPLATE-04 — Paste a CV design screenshot → generate a reusable {{ candidate.* }}-bound HTML/Jinja2 template under templates/cv/, matched to the design via a bounded WeasyPrint compare==ship loop (cap 5, diff-ratio ≤ 0.10, keep-best).

**Why human:** this flow's behavior is grounded in real command output that requires human judgment or a live environment this plain-python3 harness cannot exercise on its own.

**Steps (live):**
```bash
python3 scripts/cv/gmj_template_lint.py --template templates/cv/<slug>.html --sample-tokens "<name>,<company>,<date>"
```

**Steps (deterministic backstop):**
No deterministic backstop exists for this step.

**Expected:** running the steps above against `.claude/commands/gmj-template.md`'s documented behavior produces the outcome described in that file's own frontmatter/body — inspect stdout/stderr and any named output paths for the concrete result.

**PASS criteria:**
- A human operator confirms the observed output/state matches TEMPLATE-04's documented behavior above by reading the real output, not by delegating to a script's exit code alone.

---

_Generated from `.claude/commands/gmj-template.md` by `scripts/gmj_testplan_gen.py`. This file is not an executable artifact — it is prose a human reads and acts on manually._
