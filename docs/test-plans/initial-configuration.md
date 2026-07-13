# Test Plan — gmj-interview

This file verifies the `gmj-interview` flow for a human operator running it directly.

## Setup & Preconditions

No preconditions — this flow has no setup requirements beyond the repo's standard `pip install` step.

## Test 1 — gmj-interview

**Proves:** INTERVIEW-01 — Gap-filling interviewer — reads the real profile + coverage manifest, asks only about real gaps one question at a time, captures search preferences behind the validator guard, and hands profile facts to gmj-candidate-configurator.

**Why human:** this flow's behavior is grounded in real command output that requires human judgment or a live environment this plain-python3 harness cannot exercise on its own.

**Steps (live):**
```bash
python3 scripts/preferences/gmj_validate_preferences.py --file <candidate-prefs-path>
```

**Steps (deterministic backstop):**
No deterministic backstop exists for this step.

**Expected:** running the steps above against `.claude/commands/gmj-interview.md`'s documented behavior produces the outcome described in that file's own frontmatter/body — inspect stdout/stderr and any named output paths for the concrete result.

**PASS criteria:**

| Pass Signal | Fail Signal | Signal Source | Semantic Caveat |
|---|---|---|---|
| `config/preferences.yaml` is written and validates against `schemas/preferences.schema.json` (root `additionalProperties: false`) **and** passes `scripts/preferences/gmj_validate_preferences.py`'s shape-plus-subset-of-`sources.yaml` check | `gmj_validate_preferences.py` rejects the file — shape violation, or a `scope.sites`/`scope.cities`/`scope.languages` array that is not a subset of `config/sources.yaml`'s corresponding array | `schemas/preferences.schema.json` (`scope.sites`/`scope.cities`/`scope.languages`, `additionalProperties: false`) + `scripts/preferences/gmj_validate_preferences.py` (subset-of-sources.yaml runtime check) | The interviewer's *gap-detection* judgment — asking only about real gaps in the candidate profile, one at a time — is an LLM judgment call; the validator gate only checks the resulting YAML's shape/subset-of-scope, never whether the interview asked the right questions |

---

_Generated from `.claude/commands/gmj-interview.md` by `scripts/gmj_testplan_gen.py`. This file is not an executable artifact — it is prose a human reads and acts on manually._
