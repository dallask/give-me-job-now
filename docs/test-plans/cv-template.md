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

| Pass Signal | Fail Signal | Signal Source | Semantic Caveat |
|---|---|---|---|
| No single pass/fail signal exists. Nearest qualitative check: `gmj_visual_diff.py`'s `diff_ratio()` returns a float in `[0,1]` (0.0 = identical) and the loop stops at <= 0.10, bounded by a cap of 5 iterations with keep-best-on-cap-reached. A separate mechanical gate runs alongside: `gmj_template_lint.py`'s `lint_template()` returns an empty list on pass — this lint IS a clean binary signal, even though the visual-match half is not | `gmj_template_lint.py` returns a non-empty list (leaked sample token or email/URL/proper-noun backstop match) — the template MUST be regenerated. Visual-diff side: the cap (5 iterations) is reached without ever hitting <= 0.10, but the agent still reports `status: success` with the best-kept version per its own output contract — a strict "fail" state for the visual-match half does not exist in the current contract | `scripts/cv/gmj_visual_diff.py` (`diff_ratio` float, pinned constants `RASTER_DPI=150`, `DIFF_SIZE=(1000,1414)`, `RESAMPLE=Image.LANCZOS`) + `scripts/cv/gmj_template_lint.py` (`lint_template()` return list, empty = pass) + `.claude/commands/gmj-template.md`'s stated cap (5, line 42: "Iteration cap `5` — never run more than 5 iterations.") + `.claude/agents/gmj-template-creator.md`'s stated threshold (<= 0.10) | The compare==ship visual-diff judgment of "is this close enough to the design" is bounded by a hard numeric threshold (<= 0.10), so the threshold check itself is mechanical — but the decision to accept a best-kept version at cap-exhaustion (rather than hard-failing) is a designed compare==ship judgment call the agent's own output contract makes explicit |

---

_Generated from `.claude/commands/gmj-template.md` by `scripts/gmj_testplan_gen.py`. This file is not an executable artifact — it is prose a human reads and acts on manually._
