# execution-log-spike

**Phase 6 Plan 01 spike artifact.** Not a real feature — this capability exists solely to prove
D-01's registration mechanism (RESEARCH.md Open Question 1: "how does a project-local GSD
capability overlay get registered into the loop-hook system from inside a downstream project?").

## What it proves

That a project-scope `capability.json` overlay, authored under
`.gsd/capabilities/<id>/capability.json` in this repo, can be:

1. **Authored** as a minimal, valid feature-role capability (per `capability-validator.cjs`'s
   `validateCapability`/`validateFeatureBody` rules).
2. **Installed with consent** via `gsd-tools capability install ./.gsd/capabilities/execution-log-spike
   --scope project --yes`.
3. **Observed active** in `gsd_run loop render-hooks execute:post --raw` output — i.e. the
   installed overlay actually merges into the runtime hook registry that every GSD workflow
   consumes at each `<point>`, not just parses/validates in isolation.

It declares a single `contribution`-kind hook at `execute:post` (the cheapest kind to prove —
no downstream skill/agent must exist to dispatch it, unlike a `step`). The fragment is an inert
HTML comment; it has zero executable surface (`hooks: []`, `skills: []`, `agents: []`, `steps: []`)
and can only ever inject static text into the `verifier` role's rendered prompt at `execute:post`.

## Superseded by Plan 03

Plan 03 authors the real production logging capability (either replacing this folder's contents
or creating a separate `execution-log` capability — see
`06-CAPABILITY-SPIKE.md`'s decision record for which). Once Plan 03 lands, this spike's
`execute:post` contribution MUST be removed or repurposed so two conflicting `execute:post`
contributions are never active from this phase at once.
