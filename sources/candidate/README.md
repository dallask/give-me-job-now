# Candidate intake

This folder is the front door for feeding your real materials into the pipeline.
Drop documents here (and/or list credential URLs) and the `candidate-analyzer`
ingests them, the `candidate-configurator` merges the findings into
`config/candidate.yaml`, and everything downstream (CV, cover letter, interview
prep) is generated **only** from that merged profile.

## How to drop documents

Put files directly in `sources/candidate/`. The analyzer globs this folder and
routes each file by type:

| You drop | How it is read |
|----------|----------------|
| `.txt` `.md` `.pdf` `.docx` `.csv` | text extraction via `python3 scripts/cv/extract.py "<file>" --json` |
| `.jpg` `.jpeg` `.png` `.webp` `.gif` `.tif` `.bmp` | read visually (vision) — a diploma/badge screenshot is transcribed |
| `.doc` (legacy binary Word) | flagged **needs-conversion** — re-save as `.docx` or PDF and drop that instead |
| anything else | attempted, and if it cannot be read it is recorded as an error — never silently dropped |

The analyzer produces a **coverage manifest** — a census of *every* file it saw
(extracted, skipped, errored, or needs-conversion) so nothing is silently
skipped. That manifest is the completeness signal for the ingestion step.

### Optional: candidate photo

To show a headshot on PDFs that support it (`templates/cv/enhancv-inspired.html`
and the ReportLab layout), drop an image here (e.g. `photo.jpg`, square-ish works
best) and point `config/candidate.yaml` at it:

```yaml
photo: sources/candidate/photo.jpg   # or contact.photo
```

Supported photo formats: common raster formats (JPEG, PNG, WebP) readable by
Pillow / ReportLab / WeasyPrint.

## Credential URLs

To have an online profile, certificate, badge, or diploma page **fetched**, add
its host to `config/credentials.yaml` under `credential_sites`:

```yaml
credential_sites:
  - https://www.linkedin.com/
  - https://www.credly.com/
  - https://your-issuer.example/
```

Notes:

- This is a **separate allow-list** from the job-board search scope in
  `config/sources.yaml`. A host here is authorized for *credential fetches only*
  — it is not thereby a permitted offer-search domain, and vice versa.
- Every credential-list fetch is logged to `.claude/logs/credential-intake.log`
  as an audit record.
- A host on **neither** list stays blocked — use the paste fallback below.

## Option C — paste-text fallback

For a credential host you cannot (or do not want to) add to the allow-list, or
for **any image** you would rather transcribe yourself, you do not need the
fetch path at all:

- **paste the page text into chat**, or
- **save a text / HTML export into `sources/candidate/`**.

The analyzer fields pasted content as **data**, exactly like a fetched page —
zero configuration, and the manifest records it with status `pasted-fallback`.

## PII discipline

- Your real personal data (name, contact, IDs) lives **only** in
  `config/candidate.yaml` — that is the single canonical home for real PII.
- **Never commit** government IDs, raw scans, or real diploma/passport images to
  git. Drop them locally for a run, but keep them out of version control.
- Any fixtures checked into this repo are **synthetic only** — never real
  candidate data.

## The grounding set

After ingestion, the merged `config/candidate.yaml` (plus its
`config/candidate.provenance.json` sidecar, which maps each fact back to its
source) is **exactly** the traceable grounding set that the Phase-5
`truth-verifier` will check every artifact claim against. Nothing reaches a CV,
cover letter, or interview-prep doc unless it traces back here.

Because of that, **ingestion completeness is a precondition for truthful
offer-targeting**: if a material was not ingested, its facts are not in the
grounding set, and the verifier will treat any claim about them as unsupported.
The coverage manifest is how you confirm every dropped file actually made it in.
