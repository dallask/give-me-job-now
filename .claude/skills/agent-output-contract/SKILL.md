---
name: agent-output-contract
description: Canonical agent_result_v1 output envelope schema for all give-me-job spokes.
---

# agent_result_v1 — output contract

Every spoke agent ends its final message with exactly one fenced `agent_result_v1` block.

## Schema

```agent_result_v1
{
  "schema": "agent_result_v1",
  "agent": "<agent name — matches .md filename without extension>",
  "pipeline_run_id": "<value from prompt, or empty string if not provided>",
  "status": "success" | "fail" | "gap_report_ready" | "handoff",
  "artifacts": [
    {"type": "<file|yaml_section|yaml_overlay|yaml_cv|gap_report>", "path": "<absolute path>"}
  ],
  "acceptance_criteria_met": ["<id from criteria_items[]>"],
  "acceptance_criteria_failed": ["<id from criteria_items[]>"],
  "next_action": "none" | "retry" | "await_user_approval" | "handoff",
  "handoff_target": null | "<agent name>",
  "notes": "<one line: key outcome, counts, or handoff reason>"
}
```

## Field rules

| Field | Rule |
|-------|------|
| `schema` | Always `"agent_result_v1"` |
| `agent` | Exact agent name (e.g. `"cv-generator"`, `"cv-reviewer"`) |
| `pipeline_run_id` | Copy verbatim from the orchestrator prompt preamble; empty string `""` if absent |
| `status` | `success` — task done; `fail` — could not complete; `gap_report_ready` — cv-composer Pass 1; `handoff` — control returned to hub |
| `artifacts` | List every file written or confirmed. Use absolute paths. Empty array `[]` on fail or handoff with no output. |
| `acceptance_criteria_met` | **ID strings from `criteria_items[]`.** Only include IDs for criteria this spoke verified as PASS. Do NOT echo the criterion text verbatim. If no `criteria_items` were passed, use `[]`. |
| `acceptance_criteria_failed` | ID strings for criteria that FAIL. Unreported IDs are counted as failed by the gate. |
| `next_action` | `none` on success; `retry` on fail; `await_user_approval` when waiting for user (cv-composer Pass 1); `handoff` when returning control |
| `handoff_target` | Null unless `status: handoff`; then name the next agent |
| `notes` | One line maximum. Include counts, key metrics, or the reason for handoff. No multiline prose. |

## Acceptance criteria ID protocol

The orchestrator passes criteria as:
```
criteria_items:
  - id: crit-yaml-parses
    text: "config/candidate.yaml parses as valid YAML"
  - id: crit-pdf-exists
    text: "PDF exists under output/cv/"
```

Return only the IDs in `met_ids` / `failed_ids`. Example:
```json
"acceptance_criteria_met": ["crit-yaml-parses", "crit-pdf-exists"],
"acceptance_criteria_failed": []
```

**Gate invariants** (cv-deliverable-gate enforces these):
- Every returned ID must exist in `criteria_items[]`; unknown IDs fail the gate.
- `set(met_ids) ∩ set(failed_ids)` must be empty.
- `len(met_ids) + len(failed_ids) ≤ len(criteria_items)` — unreported items are counted as failed.

## Status mapping

| Condition | status | next_action |
|-----------|--------|-------------|
| All criteria met, file written | `success` | `none` |
| Any criterion failed or error | `fail` | `retry` |
| cv-composer Pass 1 gap report written | `gap_report_ready` | `await_user_approval` |
| Prototype image detected, hub must redirect | `handoff` | `handoff` |
