# CHANGELOG

<!-- version list -->

## v11.1.0 (2026-07-13)

### Bug Fixes

- **quick-260713-qy8**: Replace 4 mirror-pruned anchor_message values in milestone-releases.yaml
  ([`b73b9cc`](https://github.com/dallask/give-me-job-now/commit/b73b9cc334166568004c6edcfe127d7d08c430e9))

### Chores

- Gitignore vacancy-oriented per-offer config/cv/*.yaml
  ([`db53250`](https://github.com/dallask/give-me-job-now/commit/db532502946bc4478b39c41a71fbc881af214144))

- Swap command hooks in settings.json for improved execution flow
  ([`1ec81fc`](https://github.com/dallask/give-me-job-now/commit/1ec81fc20a5560c0f7b8f829e877cb8009850915))

- **publish**: Swap in gmj-core sample config + public README/LICENSE for public mirror
  ([`5e026ea`](https://github.com/dallask/give-me-job-now/commit/5e026ea5bebf3f1ef6a8cece5376527ca139c368))

- **quick-260713-qgp**: Stop tracking .planning/execution-logs/*.jsonl
  ([`5927993`](https://github.com/dallask/give-me-job-now/commit/5927993ae804d3f14666cf8eacbf6e2f034a011e))

### Documentation

- **quick-260713-qgp**: Backfill v11.0.0 release entry in milestone-releases.yaml
  ([`10bc7ad`](https://github.com/dallask/give-me-job-now/commit/10bc7ad34c0223277ab352ba16f76b3387474344))


## v11.0.0 (2026-07-13)

### Bug Fixes

- Mirror gmj_execution_log_writer.py into gmj-core payload
  ([`b641c9c`](https://github.com/dallask/give-me-job-now/commit/b641c9c9083ff994c708c1d56cb514ad76a021a8))

- Rebuild gmj-core payload manifest after wave 1
  ([`90fa8f8`](https://github.com/dallask/give-me-job-now/commit/90fa8f816d985a21002997b2760caccdfd03575f))

- Resolve post-merge conflicts from wave 1
  ([`feca060`](https://github.com/dallask/give-me-job-now/commit/feca0607843770f884fc311991fd2b93a9c41a43))

- Resolve post-merge conflicts from wave 1
  ([`7c0d2b7`](https://github.com/dallask/give-me-job-now/commit/7c0d2b7c8d9fbb7eef16fd5af97af6c1b133dae3))

- Resolve post-merge conflicts from wave 1
  ([`8a20d5c`](https://github.com/dallask/give-me-job-now/commit/8a20d5c53d119ff833ff64b6f697b3c952425d47))

- Resolve post-merge conflicts from wave 1 (phase 07)
  ([`1efd833`](https://github.com/dallask/give-me-job-now/commit/1efd8331be9b565d9459f0e084b35ec67ca19a9d))

- **01**: Allowlist forward-referenced gmj_testplan_gen.py in docs-currency gate
  ([`3611b2b`](https://github.com/dallask/give-me-job-now/commit/3611b2b9c4467d437e361580a95a1eba45416ac1))

- **02**: CR-01/CR-02 fold soft-wrapped numbered behaviors and skip code-block comments
  ([`2471d6f`](https://github.com/dallask/give-me-job-now/commit/2471d6f1735aef345aa886e18d47b2ffc98bb82b))

- **02**: Lock the shared rotation-counter read-modify-write with fcntl.flock (CR-02)
  ([`86b25ab`](https://github.com/dallask/give-me-job-now/commit/86b25ab5999814e7005ae148aaaa009b48b0b7f9))

- **02**: Route render_reportlab() expertise skills through expertise_skills_text()
  ([`fea1d16`](https://github.com/dallask/give-me-job-now/commit/fea1d161a16d9a09e02e367c70e3a88eb0e8a7d3))

- **02**: WR-01 tighten no_bypass_flag heuristic to reject wide co-occurrence false positives
  ([`21e30e4`](https://github.com/dallask/give-me-job-now/commit/21e30e4ba3871cd749e892dbbe56d320c8c97aea))

- **02**: WR-02 add structural test proving behaviors never leak prose bypass tokens
  ([`8520a59`](https://github.com/dallask/give-me-job-now/commit/8520a59777d934edd165a27167aacceee33e3153))

- **02**: WR-03 strip requirement-ID parenthetical wherever it occurs in description
  ([`3fae47f`](https://github.com/dallask/give-me-job-now/commit/3fae47f8359f483406ae26ad29a9831bfbb30177))

- **02**: WR-04 stop silently dropping flags with no purpose separator
  ([`0f1fb2b`](https://github.com/dallask/give-me-job-now/commit/0f1fb2beacbe33481755f9c3d58bb0ca1a70f7c3))

- **02-05**: Per-item content guard for Education (baxter.html + ReportLab)
  ([`7adb0fe`](https://github.com/dallask/give-me-job-now/commit/7adb0fed1b42edb60d1be83437722cb5864b769c))

- **02-05**: Self-correcting Certifications bullet CSS + regression test
  ([`1604849`](https://github.com/dallask/give-me-job-now/commit/1604849baba29e3068f87909163245552723fc61))

- **03**: CR-01 stop cross-section prose leaking into captured Steps commands
  ([`75aeb71`](https://github.com/dallask/give-me-job-now/commit/75aeb712b2b6f9c4998050f18ebda20e1744a38c))

- **03**: CR-01/CR-02/CR-03 regenerate docs/test-plans/*.md with corrected Steps content
  ([`25ba948`](https://github.com/dallask/give-me-job-now/commit/25ba94850850f4a546dc8f0d7ec0e2a56d9efbd2))

- **03**: CR-02/CR-03 keep slash-command follow-up steps and split independent alternatives into
  judgment-gated sub-blocks
  ([`99275d3`](https://github.com/dallask/give-me-job-now/commit/99275d3b63e7037ba293e7fd45b97183601db0e3))

- **03**: WR-02 fail closed when --all is combined with single-invocation-only flags
  ([`f4459e2`](https://github.com/dallask/give-me-job-now/commit/f4459e22f1b1498199fff6d1b676df38cd5b6b5f))

- **03**: WR-03 distinguish exception type in FAIL: messages for easier CI triage
  ([`56c4454`](https://github.com/dallask/give-me-job-now/commit/56c4454516cc3f40dcfe1ac49f3833ee5880847f))

- **04**: Correct gmj-truth-verifier naming in signal-table caveat
  ([`6174d67`](https://github.com/dallask/give-me-job-now/commit/6174d67cab9002a1d7676da1e95a05a95cdf7237))

- **04**: Update stale sdk_runner test + regenerate .cursor/agents mirror
  ([`3a90c57`](https://github.com/dallask/give-me-job-now/commit/3a90c574254c4fd959409740a308fb2cb43140d4))

- **04-03**: Split claude REPL-entry from slash follow-up into two fenced blocks
  ([`c6dfcca`](https://github.com/dallask/give-me-job-now/commit/c6dfcca9e0d0a97b22e3cf77392dde20c67e3bcb))

- **04-03**: Un-escape pipe artifacts and add em-dash separator in signal table data
  ([`a831f7c`](https://github.com/dallask/give-me-job-now/commit/a831f7cc86e183fd95fcf54afe15d9e95412005b))

- **04-04**: Regenerate docs/test-plans against 04-03's fixed source
  ([`c7828c2`](https://github.com/dallask/give-me-job-now/commit/c7828c2c56b59dfb6b6efd773d57aec495bd8013))

- **06**: CR-01 prefer most-recently-modified STATE.md over hardcoded top-level precedence
  ([`5b1dc08`](https://github.com/dallask/give-me-job-now/commit/5b1dc08cfb7a4d3a5f0c478b0e016f3a67876aa9))

- **06**: WR-01 add wall-clock timeout guard to python3 subprocess calls
  ([`4ed46ec`](https://github.com/dallask/give-me-job-now/commit/4ed46ecb0b0aed2dd88e5ad4709fbdbafd38d3d1))

- **06**: WR-02 stop overloading --plan with descriptive phase-name label
  ([`591d8c0`](https://github.com/dallask/give-me-job-now/commit/591d8c02fcf672cdb02c58b58962325c8be632b1))

- **06**: WR-03 add regression tests for STATE.md discovery precedence
  ([`97e9ab7`](https://github.com/dallask/give-me-job-now/commit/97e9ab74a58c5384b746a0259d4618402114c0d3))

- **07-02**: Raise loud error on unresolvable repo root instead of guessing (PIPEFIX-04)
  ([`2b0bacf`](https://github.com/dallask/give-me-job-now/commit/2b0bacf4b39a408131e22e304b4423b47b64a188))

- **publish**: Exclude PII leak file and dead CI surface from public mirror
  ([`57a70e7`](https://github.com/dallask/give-me-job-now/commit/57a70e7e5a4a1d482536996ab6cf50f642a3171b))

### Chores

- Remove execution-log-spike capability and documentation
  ([`eb3b70a`](https://github.com/dallask/give-me-job-now/commit/eb3b70a31bc65627da55726d906444fe4d22d80a))

- **02**: Remove PLANNED_SCRIPTS allowlist entry for gmj_testplan_gen.py
  ([`c0d641a`](https://github.com/dallask/give-me-job-now/commit/c0d641a77d70203755cd8a2e2eb8eb1b3ec06f17))

- **03**: Rebuild gmj-core payload after adding gmj_check_milestone_releases.py
  ([`78de7f5`](https://github.com/dallask/give-me-job-now/commit/78de7f51bf3652fec4dd49179409277b41abdac6))

- **260712-i9v**: Delete public-assets/ (superseded by root README.md/LICENSE)
  ([`da9e3d7`](https://github.com/dallask/give-me-job-now/commit/da9e3d7d6755a602a2f743989359f7b8e444215e))

- **publish**: Exclude 3 internal docs from public mirror
  ([`c181302`](https://github.com/dallask/give-me-job-now/commit/c181302e8e9efaa629644f22008d34555a3cc94e))

- **publish**: Remove stale TUI/ exclusion entry from paths-to-remove.txt
  ([`70d20ee`](https://github.com/dallask/give-me-job-now/commit/70d20ee76c23f635edb54bad8ad7ff23a5c4b69e))

### Documentation

- **04-04**: Document bounded HOOK_ERROR retry protocol in gmj-orchestrator.md
  ([`7487781`](https://github.com/dallask/give-me-job-now/commit/748778164600d9ee64ab5e3b5d5cabc1c4216e1e))

- **04-05**: Add JSON-escaping guidance for free-text envelope fields
  ([`852f2d4`](https://github.com/dallask/give-me-job-now/commit/852f2d4babcfca94c1e4f86b6aa727fac9c2c669))

- **05-01**: Wire test_testplans_current.py into docs-currency gate checklist
  ([`1e2f35f`](https://github.com/dallask/give-me-job-now/commit/1e2f35fbe9222809ae278c8b8602fe1a60057bcc))

- **06-05**: Confirm .gitignore coverage for self-reflect-report.md
  ([`de6299a`](https://github.com/dallask/give-me-job-now/commit/de6299acccf9a02adbb7878bcb2d0870ce023101))

- **07-01**: Wire explicit cap-bump instruction into Exit-2 branch (PIPEFIX-01)
  ([`058d3f0`](https://github.com/dallask/give-me-job-now/commit/058d3f02e74f05c5f0b57b9a7996066f7c71d5e3))

- **260712-i6t**: Add Features section to README.md
  ([`e72655a`](https://github.com/dallask/give-me-job-now/commit/e72655ac4831edde235169694778f9e114309bec))

- **260712-i9v**: Update publish runbook + path-removal list for root docs
  ([`f629221`](https://github.com/dallask/give-me-job-now/commit/f629221ee3d316182f05752927127d3a421ea8c7))

- **260712-n1r**: Describe wizard output in installation.md; close installer next-steps todo
  ([`bcfdedd`](https://github.com/dallask/give-me-job-now/commit/bcfdedd08a8ee52cfcb7fc11b88073572b52fa11))

- **agent**: Clarify liveness signal source for WebFetch/Firecrawl fetch in gmj-offer-scout
  ([`de5ee44`](https://github.com/dallask/give-me-job-now/commit/de5ee449944f9a0d2e28a2bd47720d023ba40fd5))

- **demo-walkthrough**: Drop dead TUI/testing-plan.md link and delete TUI/
  ([`9a2b8c7`](https://github.com/dallask/give-me-job-now/commit/9a2b8c75e9eedd1c8193e04c82da436ca8072d7e))

- **quick-260712-i1i**: Add Warning section and TOC entry to public README
  ([`f8d6f33`](https://github.com/dallask/give-me-job-now/commit/f8d6f33c548aad1b4816deb14f6818391743f83f))

- **quick-260712-i1i**: Sync intro/Quickstart/doc-index wording into public README
  ([`51f7866`](https://github.com/dallask/give-me-job-now/commit/51f786611b2239b76c96538ca1011d891437e3c6))

### Features

- Add active-development warning (README section + site modal)
  ([`d35b7cf`](https://github.com/dallask/give-me-job-now/commit/d35b7cf40bc9e0a29b06636fbf1f7a5595a8a8bc))

- Implement proactive pipeline guidance for offer liveness and dependency checks
  ([`b7d7368`](https://github.com/dallask/give-me-job-now/commit/b7d736822ba2d9c63ab92b3ce5ee9f3abad5f3d1))

- **02-01**: Author gmj-cleanup-wizard.md slash-command doc
  ([`dfae0e9`](https://github.com/dallask/give-me-job-now/commit/dfae0e9fc9db00dce8b34e18e3a196afb06449f9))

- **02-02**: Build extract() to parse command-file frontmatter/body into IR
  ([`e56bfbd`](https://github.com/dallask/give-me-job-now/commit/e56bfbd8049ae332fb8f08aeee9ed1a8aa5bcbdb))

- **02-02**: Build render() + write_testplan() + wire CLI main()
  ([`5cc0561`](https://github.com/dallask/give-me-job-now/commit/5cc0561d8cb17d3728f90796150e5cf47fae83c4))

- **02-03**: Generate cleanup-wizard test plan, fix two extractor bugs
  ([`511505a`](https://github.com/dallask/give-me-job-now/commit/511505aa3d13b191638d602bd3a628b7c067f22a))

- **02-04**: Fall back to master candidate.yaml photo for skill-CV renders
  ([`0bb1eda`](https://github.com/dallask/give-me-job-now/commit/0bb1edadfbe3b71cb63a7adbb93e2208935f7937))

- **02-04**: Strip embedded label prefixes and trailing punctuation in contact_lines()
  ([`4357a67`](https://github.com/dallask/give-me-job-now/commit/4357a674c533c7dff9466ca0d19522c33317b709))

- **02-05**: Add expertise_skills_text() type-safe helper, wire into baxter.html
  ([`dcef6b1`](https://github.com/dallask/give-me-job-now/commit/dcef6b10680cdc9add94989bef5403077bbd29c3))

- **03-01**: Add risk_tier validation and tier-aware warning block to gmj_testplan_gen
  ([`87e7948`](https://github.com/dallask/give-me-job-now/commit/87e7948ad03fa86bf38cbc93cef58ae6aa2a383a))

- **03-02**: Add FLOW_MANIFEST resolving the 3 open design questions
  ([`bf212fc`](https://github.com/dallask/give-me-job-now/commit/bf212fc8f6675eeb1baaedb2b7da244f50ca74f8))

- **03-02**: Extend main() with manifest-driven --all multi-flow mode
  ([`1a2b8a6`](https://github.com/dallask/give-me-job-now/commit/1a2b8a66095bb65e364516f74cef32b9d75321af))

- **03-03**: Run test-plan generator for real, add 10-file rollout regression test
  ([`cb4d6a1`](https://github.com/dallask/give-me-job-now/commit/cb4d6a148d6f5ee7d319f2a0e78a9b8504bab179))

- **04-01**: Add verbatim signal-table data module (Task 1)
  ([`d3c397c`](https://github.com/dallask/give-me-job-now/commit/d3c397c63773da0591147547b504adecead036df))

- **04-01**: Thread signal_table through extract()/render() (Task 2)
  ([`e71de3f`](https://github.com/dallask/give-me-job-now/commit/e71de3fc62fc8559e0fc125fda0e6481051f6c94))

- **04-02**: Regenerate all 10 docs/test-plans/*.md via real --all CLI + add real-file regression
  tests
  ([`4c4019f`](https://github.com/dallask/give-me-job-now/commit/4c4019f3f7a2d06d9497dc28a87da56660886e0b))

- **04-02**: Wire SIGNAL_TABLE_BY_SLUG into _run_all_mode() with fail-closed per-row guard
  ([`2e4d4a5`](https://github.com/dallask/give-me-job-now/commit/2e4d4a59ec65c991fb8170ea0dbadb92bd7ae721))

- **04-04**: Add gmj_check_envelope_retry.py bounded contract-violation retry cap
  ([`32bed2b`](https://github.com/dallask/give-me-job-now/commit/32bed2b989d3bce49e2fc5e376d0d524379b1d4e))

- **04-05**: Repair bare-backslash escape errors before json.loads()
  ([`11894b6`](https://github.com/dallask/give-me-job-now/commit/11894b6c4179e3016e3d2670989c81cd7ac05520))

- **04-06**: Add mandatory final_turn preamble to every Task(<spoke>) dispatch
  ([`966fc5d`](https://github.com/dallask/give-me-job-now/commit/966fc5d9f9c192c39587e748f9a42b11e56649ce))

- **04-06**: Add worked-example agent_result_v1 block to all 5 spoke docs
  ([`22e9474`](https://github.com/dallask/give-me-job-now/commit/22e947460f0dd3aba06cde7d460285394b69ba64))

- **04-07**: Resolve bare agent_result_v1 envelopes in gmj_validate_envelope.py
  ([`cb981a5`](https://github.com/dallask/give-me-job-now/commit/cb981a5cf45c6dcd1f014f2907f11054447f45d7))

- **05-01**: Implement drift-detection gate for signal-table citations
  ([`a6ef7e7`](https://github.com/dallask/give-me-job-now/commit/a6ef7e7db154703f8c8486913768a35dfa3eb894))

- **06-01**: Author execution-log-spike capability overlay
  ([`99b4685`](https://github.com/dallask/give-me-job-now/commit/99b4685ac38f3e26ad796fa71987e2607ae76ab5))

- **06-01**: Implement gmj_check_leftover_artifacts.py (CLEAN-01)
  ([`71fe18b`](https://github.com/dallask/give-me-job-now/commit/71fe18b8e29e1a8063e3b3c19487444d905814d9))

- **06-02**: Add gmj-execution-log.sh tool-call JSONL capture hook
  ([`5fed404`](https://github.com/dallask/give-me-job-now/commit/5fed404817ac6f6a9b49da5d680cef1e25852a57))

- **06-02**: Freeze leftover_artifacts_default via CLEAN-03 config contract
  ([`6cb041e`](https://github.com/dallask/give-me-job-now/commit/6cb041e3c64d694737bd72646dbe02fb6446551e))

- **06-02**: Wire gmj-execution-log.sh into settings.json hook matchers
  ([`d98b2f7`](https://github.com/dallask/give-me-job-now/commit/d98b2f7fd90539da2db29dba56001a7709f0b0f7))

- **06-03**: Add gsd-workflow-layer JSONL execution-log writer (fallback path)
  ([`6aa3348`](https://github.com/dallask/give-me-job-now/commit/6aa3348fe79d26a713c71eaf85d963f58b658314))

- **06-03**: Wire CLEAN-01/02/03 into gmj-orchestrator.md's init_run
  ([`3f75506`](https://github.com/dallask/give-me-job-now/commit/3f75506de363fee5f8451d97a09104272faf9bd9))

- **06-04**: Add gmj_self_reflect.py report-only analyzer + core tests
  ([`55fa356`](https://github.com/dallask/give-me-job-now/commit/55fa3566f9a2bd2af2089374762f48ab11e7670e))

- **06-05**: Add /gsd-self-reflect report-only command
  ([`8dc262a`](https://github.com/dallask/give-me-job-now/commit/8dc262abdfc2aae0831f51442face6313c5effbe))

- **06-05**: Implement gmj_self_reflect_apply.py single-fix applier
  ([`d8a2cfc`](https://github.com/dallask/give-me-job-now/commit/d8a2cfca00984e94af34fb353f9e9079758f725e))

- **06-06**: Auto-fire bounded self-reflect analyzer from dispatch hook (Task 2)
  ([`d1bf2ff`](https://github.com/dallask/give-me-job-now/commit/d1bf2ff77abfb58b3f07083520fcf3b078aa330e))

- **06-06**: Build Stop-event dispatch hook, wire into settings.json (Task 1)
  ([`2b1b2e0`](https://github.com/dallask/give-me-job-now/commit/2b1b2e0d666017ecbb6673b564b6009b9d39dfb0))

- **06-07**: Add session-scoped workstream resolution tier to dispatch hook
  ([`7d098a3`](https://github.com/dallask/give-me-job-now/commit/7d098a3929a760d8d643f638d850e1ea2975d3d2))

- **07-01**: Add gmj_check_cap.py atomic --new-cap write flag (PIPEFIX-01)
  ([`2cecb7b`](https://github.com/dallask/give-me-job-now/commit/2cecb7b93bb468d8fd40758f8ddccc88bad34da2))

- **07-03**: Wire Read into PreToolUse execution-log matcher (REFLECT-06)
  ([`1eb7cb7`](https://github.com/dallask/give-me-job-now/commit/1eb7cb7902443921303a1fd36ba30e4b682ea872))

- **07-04**: Add mandatory pre-turn-end self-check to gmj-artifact-composer
  ([`4d0d481`](https://github.com/dallask/give-me-job-now/commit/4d0d481dac34d941c9d91a00b7ca70b4aa3f54e6))

- **07-04**: Grant gmj-fit-evaluator and gmj-truth-verifier a scoped Write tool
  ([`c048c6a`](https://github.com/dallask/give-me-job-now/commit/c048c6a64ef5488b6d52a0da310446c211b4ccee))

- **07-05**: Harden education-row rendering with single-owner validation helper (PIPEFIX-02)
  ([`c705ca0`](https://github.com/dallask/give-me-job-now/commit/c705ca09f73da382dad2e8d0f654c37b6c5b6cf5))

- **07-06**: Add gmj-pipeline-cap-raise-misuse pattern detector (REFLECT-07)
  ([`855934c`](https://github.com/dallask/give-me-job-now/commit/855934c28c8ecc469fb2bd1afdc1c45a2c4563a5))

- **260712-i9v**: Add PRIVATE-ONLY/PUBLIC-MIRROR marker blocks to README.md
  ([`876e042`](https://github.com/dallask/give-me-job-now/commit/876e04244a4f5f09f5242e3cc244ce25fbf1129c))

- **260712-i9v**: Create root LICENSE (verbatim MIT text)
  ([`903444a`](https://github.com/dallask/give-me-job-now/commit/903444a72e91bfe2a69af370cf052f6205118b90))

- **260712-i9v**: Source doc-injection from root README.md/LICENSE
  ([`33dbc4d`](https://github.com/dallask/give-me-job-now/commit/33dbc4df90b5283f31aa86659e9705b9b6e1670e))

- **260712-mm2**: Install.sh full requirements aggregation, Python 3.9 floor, OS/WSL label,
  post-install smoke check
  ([`ea89d18`](https://github.com/dallask/give-me-job-now/commit/ea89d184dad395f0bef58f4922a3ba7e05fec50e))

- **260712-n1r**: Add wizard UI layer to install.sh
  ([`a29be97`](https://github.com/dallask/give-me-job-now/commit/a29be9768b4278eb79fbd45b3b8b29c87d5b2bfb))

- **publish**: Add missing v8.0.0 and v10.0.0 release entries
  ([`2300edf`](https://github.com/dallask/give-me-job-now/commit/2300edff1d0495d934caa2fa53140051a760294b))

- **site**: Add homepage Features section; fix raw-url doc placeholders
  ([`a365888`](https://github.com/dallask/give-me-job-now/commit/a36588875abdcb522aa9ee979c85942b8933e6ea))

### Testing

- **02-03**: Add drift-guard regression test for cleanup-wizard.md
  ([`1205fc6`](https://github.com/dallask/give-me-job-now/commit/1205fc64f210463f51b324b335f4c8b5de79c6b0))

- **02-04**: Add failing tests for contact_lines label/punctuation stripping
  ([`8cfe0b5`](https://github.com/dallask/give-me-job-now/commit/8cfe0b5354830ab719970a244c561c6bf18abe21))

- **02-04**: Add failing tests for skill-CV master-photo fallback
  ([`cc9d190`](https://github.com/dallask/give-me-job-now/commit/cc9d190d560ca26c144924f31128d09b2cb66a3a))

- **02-05**: Add failing tests for expertise_skills_text() type-safe helper
  ([`98cb6c7`](https://github.com/dallask/give-me-job-now/commit/98cb6c7bfc4d1dc69420b99872367531c2ebaff9))

- **03**: WR-01 add cross-section leak, slash-command, and alternatives regression tests
  ([`6025aa5`](https://github.com/dallask/give-me-job-now/commit/6025aa5a2b6e438ac9bf84a937de75d3d87f771a))

- **03-02**: Add advisory + SC3-proof wrapper for milestone-releases check
  ([`81bad08`](https://github.com/dallask/give-me-job-now/commit/81bad083bd13ee59da7056eca3ef0711aa0d4fea))

- **04-03**: Add failing regression test for CR-01 single-block bundling
  ([`123623a`](https://github.com/dallask/give-me-job-now/commit/123623a7caa0757ae30651066e1d7c8f8ae09d1d))

- **04-03**: Add failing regression tests for CR-02/CR-03 and adjust affected pre-existing
  assertions
  ([`87c6d8c`](https://github.com/dallask/give-me-job-now/commit/87c6d8c0201a1aba2cb815e752242c82c77f643e))

- **04-04**: Add 3 real-file regression tests for CR-01/CR-02/CR-03
  ([`3c87afc`](https://github.com/dallask/give-me-job-now/commit/3c87afcc69ee2965b93c6c68a429225da68220f2))

- **04-04**: Doc-lint the HOOK_ERROR retry protocol into gmj-orchestrator.md
  ([`ca7e6db`](https://github.com/dallask/give-me-job-now/commit/ca7e6db1fc707fe1999ecbedf848644be71b5440))

- **04-05**: Add failing regression tests for bare-backslash escape repair
  ([`a2d1446`](https://github.com/dallask/give-me-job-now/commit/a2d1446fae118fb50b116903ba3a3f84b919e439))

- **04-06**: Lock final_turn preamble + worked-example mechanism into doc-lint suite
  ([`fcf10dc`](https://github.com/dallask/give-me-job-now/commit/fcf10dc3d6750130ce6521f58923b87738bf5b61))

- **04-07**: Add agent_result_v1.valid.json fixture + --file mode coverage
  ([`4098720`](https://github.com/dallask/give-me-job-now/commit/40987202220869dd023dd5ac280422047031d939))

- **05-01**: Add failing drift-detection gate for signal-table citations
  ([`d5c6068`](https://github.com/dallask/give-me-job-now/commit/d5c60684b48e52f88aeec3c170153d3b9ed226ef))

- **06-01**: Add failing test contract for gmj_check_leftover_artifacts.py
  ([`5d1dc10`](https://github.com/dallask/give-me-job-now/commit/5d1dc10592cec01dead6873e0140da4e204e07b9))

- **06-02**: Add failing test for leftover_artifacts_default freeze contract
  ([`61ac0dd`](https://github.com/dallask/give-me-job-now/commit/61ac0dde8abba19f06db0b6e44ed6ac4b5985265))

- **06-03**: Extend test_orchestrator_wiring.py with CLEAN-01/02/03 doc-lint assertions
  ([`f6b036e`](https://github.com/dallask/give-me-job-now/commit/f6b036eef2a4b8598e29cdb748f07a3fcd1bb7f1))

- **06-04**: Add named acceptance-bar pattern fixtures for self-reflect
  ([`91d5a31`](https://github.com/dallask/give-me-job-now/commit/91d5a317803b2482b9de1ce69153ee021d27e58f))

- **06-05**: Add failing tests for gmj_self_reflect_apply.py
  ([`3fd5663`](https://github.com/dallask/give-me-job-now/commit/3fd5663f67735fcec1b07b32afd17d57a03915b7))

- **06-06**: Add failing tests for bounded self-reflect auto-fire (Task 2)
  ([`09ac3b9`](https://github.com/dallask/give-me-job-now/commit/09ac3b9958b0137b0ea780073318a6611066f5d6))

- **06-06**: Add failing tests for Stop-event dispatch hook (Task 1)
  ([`5131837`](https://github.com/dallask/give-me-job-now/commit/513183746b152827250a6960f4f0ba61ded62da6))

- **07-01**: Add failing tests for gmj_check_cap.py --new-cap flag
  ([`695de5c`](https://github.com/dallask/give-me-job-now/commit/695de5c816f540ead194ff86941e70cec1dcf4e9))

- **07-03**: Add Read-shaped fixture and regression test (REFLECT-06)
  ([`d72aa70`](https://github.com/dallask/give-me-job-now/commit/d72aa704dcbd4377e70f9f45381ce0e75ab6c7c3))

- **07-06**: Add failing test for gmj-pipeline-cap-raise-misuse detector (REFLECT-07)
  ([`5aeb677`](https://github.com/dallask/give-me-job-now/commit/5aeb677efeeafa8be30d37afce6f6e03f4b86083))

- **260712-mm2**: Regression coverage for requirements aggregation, version floor, smoke check +
  docs refresh
  ([`2bb7411`](https://github.com/dallask/give-me-job-now/commit/2bb7411c16c42b6b785fb1326beaaf28a9c528a2))

- **260712-n1r**: Add regression tests for the wizard UI layer
  ([`405d9fb`](https://github.com/dallask/give-me-job-now/commit/405d9fbfba9d55ad0e7fe9d09a2ee47fefed8375))


## v10.0.0 (2026-07-11)

### Bug Fixes

- Resolve post-merge conflict from wave 1 — regenerate stale .cursor/agents/ mirrors
  ([`ccec342`](https://github.com/dallask/give-me-job-now/commit/ccec3424f92e40d19375a14ddfb25063118ff001))

- **04-02**: Accept entries key alias in gmj_merge_shortlists, fail loud otherwise
  ([`eb9726c`](https://github.com/dallask/give-me-job-now/commit/eb9726c1e2e9865e601009a3647852eeb2e1a214))

- **publish**: Anchor v5.0.0/v6.0.0/v7.0.0 to commits that survive the mirror's git-filter-repo
  rewrite
  ([`fe9ca1e`](https://github.com/dallask/give-me-job-now/commit/fe9ca1e9aa5214b8d5f4eec5b368976a38b13fc9))

- **release**: Use PUBLIC_REPO_PAT for checkout's token: input, not just step-level GH_TOKEN
  ([`14ed39f`](https://github.com/dallask/give-me-job-now/commit/14ed39fe3bd1aefc378e01e7921de085e6072b58))

- **release**: Use PUBLIC_REPO_PAT instead of GITHUB_TOKEN for tag/release pushes on the mirror
  ([`8024fd8`](https://github.com/dallask/give-me-job-now/commit/8024fd8c37f95c268e2dd26c476620d03e2ae169))

### Documentation

- **04-01**: Reinforce gmj-offer-scout.md's canonical shortlist key emphasis
  ([`7193eb6`](https://github.com/dallask/give-me-job-now/commit/7193eb6c6766975c57bb0421c61306d506df90c9))

### Features

- **03-01**: Backfill v9.0.0 entry in milestone-releases.yaml
  ([`b7aa4d2`](https://github.com/dallask/give-me-job-now/commit/b7aa4d2c122f8413a6f56add0efb04855bcf38c3))

- **03-02**: Add gmj_check_milestone_releases.py gap-detection CLI
  ([`84b10d9`](https://github.com/dallask/give-me-job-now/commit/84b10d916221c6520675d39e70d6b68a9e6646a6))

- **04-01**: Harden agent_result_v1 closing instruction across all 5 collective agents
  ([`d44073d`](https://github.com/dallask/give-me-job-now/commit/d44073d3514bf17d18786798100e503d6d578fed))

### Testing

- **03-08**: Lock TMPL-04 languages-row-explosion with regression assertion
  ([`075543d`](https://github.com/dallask/give-me-job-now/commit/075543d2eb97978505f8b13d122dcc7db464dbf8))

- **04-01**: Doc-lint tests proving uniform closing-instruction hardening + D-06 emphasis
  ([`a72df33`](https://github.com/dallask/give-me-job-now/commit/a72df3366fa36513b8000e58d2ce7bb7d3398c21))


## v9.0.0 (2026-07-11)

### Bug Fixes

- Resolve post-merge conflicts from wave 1
  ([`d4daf27`](https://github.com/dallask/give-me-job-now/commit/d4daf27304aae7afe18e7f12545e00b1b7fbdea4))

- **01-01**: Correct double-backtick nesting around slash commands in README Quickstart
  ([`9ef53fb`](https://github.com/dallask/give-me-job-now/commit/9ef53fb5bb010b86714eb0a051c41756c6cb85e7))

- **02**: Rebuild gmj-core payload to include new CV template config module
  ([`7e6012a`](https://github.com/dallask/give-me-job-now/commit/7e6012a97bdc946f04d9a2ae704259681a673771))

- **02**: Regenerate .cursor/agents mirror after gmj-cv-generator.md update
  ([`bb06566`](https://github.com/dallask/give-me-job-now/commit/bb0656666952553242b35a89331207ea54a2d932))

- **03-02**: Drop trailing no-op pilot.pause() in _probe_docs_reopen_after_change
  ([`ed7766e`](https://github.com/dallask/give-me-job-now/commit/ed7766e7f13f1e91b2928d4b00c636ebf70f1bf1))

- **03-02**: Omit resume_title heading and dash-join header when absent in render_reportlab
  ([`4beacf0`](https://github.com/dallask/give-me-job-now/commit/4beacf0c7267043747b87b4b3c5880bda6f5f016))

- **03-03**: Guard default.html dash-joins and resume_title omission
  ([`253cb14`](https://github.com/dallask/give-me-job-now/commit/253cb143eb32e36a4ab98e4834eacc028f3cf642))

- **03-03**: Guard enhancv-inspired.html dash-join and skill-group-label
  ([`2b45f56`](https://github.com/dallask/give-me-job-now/commit/2b45f56299d7eae2f66cbd6b7f8288fc80657433))

- **03-03**: Guard enhancv-left.html dash-joins and resume_title omission
  ([`9ba2b41`](https://github.com/dallask/give-me-job-now/commit/9ba2b412733e5dcc0e1412117bfb153b7e94775e))

- **03-04**: Guard enhancv/gmj-baseline resume_title and dash-join fields
  ([`0ffbea7`](https://github.com/dallask/give-me-job-now/commit/0ffbea72cc8946cb92cd2a7851dc59b951d7b26b))

- **03-04**: Guard mark-smith-navy.html experience dash-join
  ([`08435f7`](https://github.com/dallask/give-me-job-now/commit/08435f787cd8b9eedb72ace3cc285ed319706c8a))

- **03-04**: Omit resume_title label when absent in anthony/baxter/emerald
  ([`400cd57`](https://github.com/dallask/give-me-job-now/commit/400cd5778fcca43d69ec8508d202cdce9cc0e701))

- **quick-260710-utq**: Fix rebrand-acceptance grep-0 false positives
  ([`b805a8c`](https://github.com/dallask/give-me-job-now/commit/b805a8c47ef31a9823d7a85b5143b57383b92656))

- **quick-260710-utq**: Fix ua CV render English-fallback heading (tech-title text-transform)
  ([`ffdc86c`](https://github.com/dallask/give-me-job-now/commit/ffdc86cb9cf9e6d36c0571d2e1baed0a6ebe9c25))

- **quick-260710-utq**: Widen CI requirements-aggregation loop to install root-level
  requirements-*.txt
  ([`1855acc`](https://github.com/dallask/give-me-job-now/commit/1855acca22f493d78cc3b1d5867fdc0567a7e698))

### Chores

- **01-03**: Untrack gitignored output/ files from git index
  ([`6ccf08f`](https://github.com/dallask/give-me-job-now/commit/6ccf08fb1e650508e52d3c3ec48df1c0e616b190))

### Documentation

- **01-01**: Expand README.md Quickstart with requirements, install, first command
  ([`44dcea6`](https://github.com/dallask/give-me-job-now/commit/44dcea6c58d6951b5d0ddfce09dce4eb976449c7))

- **01-02**: Add mandatory resume completeness backstop + Result section to gmj-batch.md
  ([`36033ff`](https://github.com/dallask/give-me-job-now/commit/36033ffdc471eed81901929a045a849085245221))

- **01-02**: Add matching completeness backstop step to orchestrator's Bounded concurrent-offer
  dispatch
  ([`3a567aa`](https://github.com/dallask/give-me-job-now/commit/3a567aab0d4fedf446bf6eacf149e2d917e2c6f2))

- **02-03**: Document D-07 config-default precedence + wire --state/--template-name in generate.md
  ([`37b45bf`](https://github.com/dallask/give-me-job-now/commit/37b45bfa894b6532437272029545bf92e8618ad1))

### Features

- **01-01**: Add v5.0.0 release entry to milestone-releases.yaml
  ([`7c2de53`](https://github.com/dallask/give-me-job-now/commit/7c2de5339e8eb99a490700f74e8d5ec27600558b))

- **01-01**: Add v6.0.0 release entry to milestone-releases.yaml
  ([`51c1ed3`](https://github.com/dallask/give-me-job-now/commit/51c1ed39feaa65faa523803d32b2994962dd8037))

- **01-01**: Add v7.0.0 release entry, verify all 8 entries via --dry-run
  ([`6bf2e99`](https://github.com/dallask/give-me-job-now/commit/6bf2e99ac3909c7c34bdd91b05f661e398785803))

- **01-01**: Implement gmj_batch.py status subcommand
  ([`a60a78c`](https://github.com/dallask/give-me-job-now/commit/a60a78cd6309ccc20d7ea790acc9efddf9b10534))

- **02-01**: Add cv: block to config/preferences.yaml
  ([`3871a5b`](https://github.com/dallask/give-me-job-now/commit/3871a5bde293291390ca5e864bc26401e16c45cf))

- **02-01**: Add self-contained $defs.cv entry to preferences schema
  ([`700673d`](https://github.com/dallask/give-me-job-now/commit/700673db23164d02659c5e175901511912d9f886))

- **02-02**: Implement gmj_cv_template_config.resolve_template (GREEN)
  ([`995591d`](https://github.com/dallask/give-me-job-now/commit/995591d2ab598d8d4ebb2e36c133798504dbb947))

- **02-03**: Wire resolve_template() into gmj_render_cv.py precedence block
  ([`9a9fbf6`](https://github.com/dallask/give-me-job-now/commit/9a9fbf6f7d81ce6ea82eca7829d6aa066a1c6f0b))

- **03-02**: Bring 17 gap _build_app call sites to refresh=0.1
  ([`c1eb7d4`](https://github.com/dallask/give-me-job-now/commit/c1eb7d4c42684bada8cb45271bbbed53c7623e59))

- **03-06**: Add languages_rows() shape-guard helper to gmj_format_fields.py
  ([`f1ce11d`](https://github.com/dallask/give-me-job-now/commit/f1ce11dfb72a231d61decbadd58d6cd85c7f7e08))

- **03-06**: Wire languages_rows() into render_reportlab() and register Jinja filter
  ([`1af0ed1`](https://github.com/dallask/give-me-job-now/commit/1af0ed19b96d0e61880d4b64abd70cfbbdb0c253))

- **03-07**: Route 4 templates' languages loop through languages_rows filter
  ([`d7c3dd6`](https://github.com/dallask/give-me-job-now/commit/d7c3dd6ef9c3ec105dfbaf86701e81c57ef0fea1))

- **03-07**: Route remaining 4 templates' languages loop through languages_rows filter
  ([`14c33d5`](https://github.com/dallask/give-me-job-now/commit/14c33d526e23e87973275cb4235751a886137cb8))

- **04-01**: Append --durations=25 to CI pytest invocation
  ([`b9b00f4`](https://github.com/dallask/give-me-job-now/commit/b9b00f4711e8adc04ca497223a12ccdb3c916720))

### Testing

- **01-01**: Add failing regression tests for gmj_batch.py status subcommand
  ([`be30171`](https://github.com/dallask/give-me-job-now/commit/be3017106452013c66eb3e54d5618ee0bfb4de57))

- **01-02**: Extend doc-lint tests to prove the completeness-backstop wiring landed
  ([`6fb3cc6`](https://github.com/dallask/give-me-job-now/commit/6fb3cc6f92c8351b6106d0f40ef880c343d86a02))

- **02-01**: Lock cv: schema happy path and fail-closed path
  ([`a4c4348`](https://github.com/dallask/give-me-job-now/commit/a4c4348d4a94c1d4e6a441164022fca4a37538cd))

- **02-02**: Add failing tests for resolve_template (RED)
  ([`045c3d5`](https://github.com/dallask/give-me-job-now/commit/045c3d5cf77bca597df1b4913657a470d0429070))

- **02-03**: End-to-end precedence/rotation/fallback regression against real CLI
  ([`0d08069`](https://github.com/dallask/give-me-job-now/commit/0d080697f544a5b0d3010e21cb964562fb61cc6e))

- **03-01**: Add malformed CV-YAML fixture for TMPL-03/04/05 regressions
  ([`169a723`](https://github.com/dallask/give-me-job-now/commit/169a7236aa87531d8c85a353e73de230761e4044))

- **03-02**: Add malformed CV-YAML fixture for TMPL-03/04/05 defect shapes
  ([`65a913d`](https://github.com/dallask/give-me-job-now/commit/65a913d1ecbdd1473975e42b424738ac17ceffc5))

- **03-05**: Add 3 TMPL-03/04/05 regression assertions to template sweep
  ([`1174b53`](https://github.com/dallask/give-me-job-now/commit/1174b5340b69dff77264d93671a9ba5fdda5fa8b))


## v8.0.0 (2026-07-10)

### Features

- **03-01**: Wire pytest-xdist parallel execution into CI (PERF-05)
  ([`7d9f30e`](https://github.com/dallask/give-me-job-now/commit/7d9f30e85a0484d84c02c6281d388699c21fc5c1))


## v7.0.0 (2026-07-10)

### Bug Fixes

- **48**: Close interpreter-flag bypass in firecrawl scope-guard hook
  ([`243e756`](https://github.com/dallask/give-me-job-now/commit/243e756d2da54127972d2f64c4cb173cb219ebe1))

- **48**: Close value-taking-interpreter-flag bypass in firecrawl scope-guard hook
  ([`6b68ba1`](https://github.com/dallask/give-me-job-now/commit/6b68ba1edcca52c735b3c1156d9a9fdab3c0f29c))

- **48**: Fail-closed hardening, JSON escaping, and -m/-c arity fix for firecrawl scope-guard
  ([`736177c`](https://github.com/dallask/give-me-job-now/commit/736177c1c930990496f2d6869009e01e09664980))

- **48**: Tighten firecrawl scope-guard invocation matching, regenerate payload
  ([`1747d9f`](https://github.com/dallask/give-me-job-now/commit/1747d9f1f2893be39f3bde713f8451752e85ac7b))

- **48-03**: Regenerate .cursor/agents/gmj-offer-scout.md mirror
  ([`70a6e2b`](https://github.com/dallask/give-me-job-now/commit/70a6e2b4296ef79cc853fa6f40d7fcd120ad69d5))

- **49**: Generalize top3 sentinel to topN, closing an out-of-range bug in the human narrowing path
  ([`6fbf668`](https://github.com/dallask/give-me-job-now/commit/6fbf6684666b7fdf608dbeff4dd88ed24d4a105c))

- **50**: Rename gmj-cron-run log filenames to gmj_cron_run (underscore) to pass docs gmj- token
  registry check
  ([`90360d4`](https://github.com/dallask/give-me-job-now/commit/90360d4527b38d941f63990c07a8e0fc3472bf85))

- **50**: WR-01 handle claude-not-on-PATH cleanly in cron wrapper
  ([`7a0eae1`](https://github.com/dallask/give-me-job-now/commit/7a0eae11b25147e9eb78fce915fdad0b68477218))

- **50**: WR-02 add regression test for claude-missing-from-PATH
  ([`7a99e9d`](https://github.com/dallask/give-me-job-now/commit/7a99e9d9ec44078db198d4892bd00d5de58f7e36))

- **51**: CR-01 per-template label mapping for missing-sections check, WR-01 tolerance unit mismatch
  ([`eb11436`](https://github.com/dallask/give-me-job-now/commit/eb114366adfd4437c6733038552cf03d69beabee))

- **51**: Regenerate stale .cursor/agents/gmj-orchestrator.md mirror after Tools-table edit
  ([`d9f58c9`](https://github.com/dallask/give-me-job-now/commit/d9f58c97ad369d3b4e0ba000ac0942208fcc086b))

- **51**: WR-03 align QA report filename convention between generate.md and gmj-orchestrator.md
  ([`758344d`](https://github.com/dallask/give-me-job-now/commit/758344de5ba056a76fa785371573d9fd08d412d2))

### Chores

- **48**: Regenerate gmj-core payload for -c bypass fix
  ([`4edbeba`](https://github.com/dallask/give-me-job-now/commit/4edbeba838a36d5a2f84e67969d2a2281f0ea79d))

- **48**: Regenerate gmj-core payload for limitations doc fix
  ([`81ab865`](https://github.com/dallask/give-me-job-now/commit/81ab86594c0d3c92674a2d77a385149caf392898))

- **48**: Regenerate gmj-core payload for scope-guard fix
  ([`76aa911`](https://github.com/dallask/give-me-job-now/commit/76aa9111d9680b248f38677221957854e311d8d6))

- **48**: Regenerate gmj-core payload for scope-guard hardening fixes
  ([`8a58e22`](https://github.com/dallask/give-me-job-now/commit/8a58e22ad2e76286a15be66dd5bcb06de8737117))

- **51**: Rebuild gmj-core payload (syncs phase 49/50/51 script/doc changes into the packaged
  install manifest)
  ([`3bd7452`](https://github.com/dallask/give-me-job-now/commit/3bd74521f1233bea3bb0b1f1e9c86ddfc6c2da07))

- **51**: Rebuild gmj-core payload after code review fix (CR-01)
  ([`ff67481`](https://github.com/dallask/give-me-job-now/commit/ff67481fa70b75e273d56bfc6bb2e5a2e4fdc142))

### Documentation

- **04**: Mark Phase 4 execution started
  ([`07336c9`](https://github.com/dallask/give-me-job-now/commit/07336c9d6bbcf53a3a99e6a88052ecef721acf8e))

- **48**: Correct and extend documented scope-guard limitations
  ([`8ec5ad4`](https://github.com/dallask/give-me-job-now/commit/8ec5ad49b45a8008684d96db3f77de4dd6a0526a))

- **50-01**: Document cron/launchd unattended-run recipe (OPS-02)
  ([`dca2096`](https://github.com/dallask/give-me-job-now/commit/dca2096fc4f8d04456c43080286219dbed128b13))

- **51-02**: Document gmj_check_render_quality.py in gmj-orchestrator.md
  ([`d7ccfbd`](https://github.com/dallask/give-me-job-now/commit/d7ccfbd02e971c88161aa301bce658a02dba6179))

- **51-02**: Wire gmj_check_render_quality.py into generate.md's render step
  ([`fc7662e`](https://github.com/dallask/give-me-job-now/commit/fc7662e81fdb97826ee64b9468e7299d34b07864))

### Features

- **48-01**: Add Firecrawl extraction schema and offers requirements.txt
  ([`070f164`](https://github.com/dallask/give-me-job-now/commit/070f1648f20ac21ae32cec165cbd4bc905b5e0fc))

- **48-01**: Add gmj_firecrawl_search.py CLI with .env credential loading
  ([`06bf216`](https://github.com/dallask/give-me-job-now/commit/06bf216cc013c850218dfc98a240b19f796c61e9))

- **48-02**: Add gmj-firecrawl-scope-guard.sh Bash PreToolUse hook
  ([`f4b28f7`](https://github.com/dallask/give-me-job-now/commit/f4b28f72364ec401de3da37b5061017ec4fb509f))

- **48-02**: Chain gmj-firecrawl-scope-guard.sh onto Bash PreToolUse matcher
  ([`a296d16`](https://github.com/dallask/give-me-job-now/commit/a296d160b1074370c4a4498d4c15ad1edd4f7835))

- **48-03**: Add opt-in search_provider key to preferences schema and config
  ([`1e0114c`](https://github.com/dallask/give-me-job-now/commit/1e0114c3bae1aacb5cc1622edce30811d9e42d96))

- **48-03**: Wire gmj-offer-scout.md to branch on search_provider
  ([`aff7bff`](https://github.com/dallask/give-me-job-now/commit/aff7bfff2c1ad377f1315ef19703519c0118e106))

- **49-02**: Add deterministic top3 selection sentinel to gmj_batch.py init
  ([`ac2937d`](https://github.com/dallask/give-me-job-now/commit/ac2937dcdb16064eb05aef90f3f5630525b9018b))

- **49-03**: Document sorted-display + AskUserQuestion narrowing in gmj-batch persona
  ([`41fc55c`](https://github.com/dallask/give-me-job-now/commit/41fc55c744b311dc45ad84ef2221693ea3ec6ff8))

- **50-01**: Add scripts/ops/gmj_cron_run.sh cron/launchd wrapper (OPS-02/OPS-03)
  ([`b6cf18a`](https://github.com/dallask/give-me-job-now/commit/b6cf18a4f9d8ab2f5652612da3fb4dfbe92ba333))

- **50-03**: Remove 'No frozen offers' empty-state caption from vacancies panel
  ([`0ecd8b0`](https://github.com/dallask/give-me-job-now/commit/0ecd8b0f6ab31cb0dbb5abbcb08ca5a2e728d152))

- **51-01**: Add gmj_check_render_quality.py — advisory-only post-render QA (QA-02/QA-03)
  ([`c8b97b7`](https://github.com/dallask/give-me-job-now/commit/c8b97b7900b1d8eee2cc5af18ff78faed8852dfa))

### Testing

- **48-02**: Prove off-allow-list Firecrawl Bash call is blocked
  ([`2869c85`](https://github.com/dallask/give-me-job-now/commit/2869c85b804734011f3c68963aedaeb7dc74fa98))

- **48-03**: Prove zero Firecrawl invocation when search_provider is unset
  ([`16c9346`](https://github.com/dallask/give-me-job-now/commit/16c934604719a0e50caea947516e0853d57ea98f))

- **49-01**: Pin shortlist score-descending write order (SELECT-05)
  ([`f2ca3cb`](https://github.com/dallask/give-me-job-now/commit/f2ca3cb38dbc46c5ddf04d3c5425a6a7851e121a))

- **49-02**: Regression-test --select top3 end-to-end via gmj_batch.py init
  ([`07cdc71`](https://github.com/dallask/give-me-job-now/commit/07cdc71843c944e01115577e0c0e1d44fd766521))

- **49-03**: Pin sorted-display, AskUserQuestion narrowing, and autonomous top3 bypass in gmj-batch
  persona
  ([`8aa7de6`](https://github.com/dallask/give-me-job-now/commit/8aa7de6a176325125a4a17dc8753153446e0d833))

- **50-01**: Add tests/test_gmj_cron_run.py — overlap-guard + argv-shape proofs
  ([`46c7134`](https://github.com/dallask/give-me-job-now/commit/46c713415a7139800a9e57291af198399a35a5f8))

- **50-02**: Prove cron wrapper never writes pipeline.config.yaml (OPS-04)
  ([`62abb79`](https://github.com/dallask/give-me-job-now/commit/62abb7981fb0fd0066395c9155a2060e353c5c4c))

- **50-03**: Pin absence of removed 'No frozen offers' empty-state caption
  ([`5149555`](https://github.com/dallask/give-me-job-now/commit/5149555636e4727a2ef7c5dffcf35d457bd13a4c))

- **51-01**: Add tests/test_check_render_quality.py — 9 tests for all three defect classes
  ([`a7c6f56`](https://github.com/dallask/give-me-job-now/commit/a7c6f5629245a4db59471d8488c8c6af21e57f7f))


## v6.0.0 (2026-07-10)

### Bug Fixes

- **41**: CR-01 fix merge() tie-break comparing mismatched tuple fields
  ([`08d3986`](https://github.com/dallask/give-me-job-now/commit/08d3986c31c998443986e832bd941001c27d8c25))

- **41**: WR-01 fix _prune_old_outputs under-pruning when CV_KEEP_LAST=0
  ([`674514e`](https://github.com/dallask/give-me-job-now/commit/674514ea695c0aff93e29e73dea447c0e4823efa))

- **41**: WR-02 correct _classify_failure docstring to match single-claim keyword matching
  ([`59e389e`](https://github.com/dallask/give-me-job-now/commit/59e389ec07f1cada1796c99784cb68c890a61ae8))

- **41**: WR-03 add explicit | e escaping to mark-smith-navy.html and enhancv.html
  ([`31979ca`](https://github.com/dallask/give-me-job-now/commit/31979ca042f85106013704cb50e08a18d71fff55))

- **41**: WR-04 document deliberate min-threshold salary-fit semantics
  ([`0f1cca2`](https://github.com/dallask/give-me-job-now/commit/0f1cca25e7af0f6a1cd2252a74e8ce680fbd7b6b))

- **41-01**: Correct stale key_achievements index in three Gate A fixtures
  ([`959f46b`](https://github.com/dallask/give-me-job-now/commit/959f46b1daf5282a5344e5fb7c419c36ffb29f12))

- **41-05**: Route 4 templates' contact/website fields through the shared contact_lines filter
  ([`3ae3865`](https://github.com/dallask/give-me-job-now/commit/3ae3865712b584edafe0d951f1b56073ed2cd045))

- **41-06**: Remove baxter.html sidebar overflow clip, add default.html certifications section
  ([`239b707`](https://github.com/dallask/give-me-job-now/commit/239b7077c7929bbd63faaebbcac6db89eca565cd))

- **42**: Add standalone .gitignore floor blocks for sources/{offers,analysis,research,vacancies}/,
  closing STRUCT-01's success criterion 1 gap found by verify-work
  ([`c8a8b8c`](https://github.com/dallask/give-me-job-now/commit/c8a8b8c354a10c0a1f1f20a42ae992aab1c882ad))

- **42**: WR-01 correct misleading independently-git-ignored claim in paths-to-remove.txt
  ([`3838930`](https://github.com/dallask/give-me-job-now/commit/38389303e14f5f646bea0c18994d954884d17839))

- **42-02**: Default gmj_render_interview_prep.py output to output/cv/, align tests
  ([`7ab1a8c`](https://github.com/dallask/give-me-job-now/commit/7ab1a8c38c25509b88a049912aea98c0c3a039aa))

- **44**: Rebuild gmj-core payload manifest after review-fix edits
  ([`9fd50a6`](https://github.com/dallask/give-me-job-now/commit/9fd50a603e9916029134081f49c9368f7d7bffb5))

- **44**: WR-01 validate --repo-root looks like this repo before treating it as a deletion boundary
  ([`7f34a75`](https://github.com/dallask/give-me-job-now/commit/7f34a7588b7abfde3b2fa8bc4e04401032455c3d))

- **44**: WR-02 report succeeded/failed/not-attempted summary on partial delete failure
  ([`cc3a85a`](https://github.com/dallask/give-me-job-now/commit/cc3a85a79f45762ee4f8e44c65b6074313b77590))

- **44**: WR-03 extract _category_path() helper to deduplicate relative-path re-derivation
  ([`9fb7da5`](https://github.com/dallask/give-me-job-now/commit/9fb7da539e4775bc1c73a2d001522cc73038ad25))

- **44-01**: Rebuild gmj-core payload to include gmj_cleanup_wizard.py
  ([`93cf959`](https://github.com/dallask/give-me-job-now/commit/93cf959cc04dbe20e853d9f91ae968ee7d33ea02))

- **46-05**: Remove superseded site/*.html source files (web/ has reached parity)
  ([`2a592d8`](https://github.com/dallask/give-me-job-now/commit/2a592d888e720ad74afda71441e9b3bd9f07293d))

- **47**: WR-01 add 3 missing gmj_*.py scripts to cli-tools catalog and correct count-discipline
  totals
  ([`3c06a17`](https://github.com/dallask/give-me-job-now/commit/3c06a177edd32574718392fd0798b8984b1338e7))

- **cv**: Add missing numpy dependency to scripts/cv/requirements.txt
  ([`79070af`](https://github.com/dallask/give-me-job-now/commit/79070af3e504eff0938429a7ba8cf1a235b33e35))

- **publish**: Add scoped gitleaks allowlist for manifest hash false positives
  ([`f8601a3`](https://github.com/dallask/give-me-job-now/commit/f8601a3c6e1a8aa3159e602350327700567e0329))

- **publish**: Run PII-denylist gate before public-docs injection, not after
  ([`dff2f90`](https://github.com/dallask/give-me-job-now/commit/dff2f900c5868bea0d46b65eabf8035d360454f4))

- **publish**: Strip own CI workflow file from the public mirror
  ([`2bc3137`](https://github.com/dallask/give-me-job-now/commit/2bc31373f61405ed7b6dc2f859f2e49bff4028e3))

- **quick-260709-kig**: Fact-sync docs sidebar count and restyle Contact to 3-column grid
  ([`45c52c5`](https://github.com/dallask/give-me-job-now/commit/45c52c5686bcb4d8cf5a8cc65da0836bcebdd14e))

- **quick-260709-kig**: Fix mobile header stray box, decouple docs-strip, right-align nav, add brand
  icon
  ([`edd6f4f`](https://github.com/dallask/give-me-job-now/commit/edd6f4f5b0a63edf16d83b5cd7b984644373d586))

- **quick-260709-kig**: Remove conflicting color utilities from Home hero CTA buttons
  ([`1381ac7`](https://github.com/dallask/give-me-job-now/commit/1381ac77d63806e016e631b2888415ef98278564))

- **release**: Prune orphaned tags before recomputing releases
  ([`6188c4d`](https://github.com/dallask/give-me-job-now/commit/6188c4dffc2c6b9128ec0369b12effde1558387c))

- **site**: Add explicit spacing between "Give" and "Me Job NOW!" in header brand
  ([`246c9a3`](https://github.com/dallask/give-me-job-now/commit/246c9a36b93128f976e82721e270da7b902ae7c2))

- **site**: Add explicit spacing between "Job" and "NOW!" in header brand
  ([`bef467c`](https://github.com/dallask/give-me-job-now/commit/bef467c82316d0860a990ce5541a6341038124c0))

- **site**: Add gate icon to footer, remove license line
  ([`8813461`](https://github.com/dallask/give-me-job-now/commit/8813461bd02eb8d3732cb2a08cb91045947d6e0c))

- **site**: Add overflow-hidden to docs.html main content area
  ([`66a3f59`](https://github.com/dallask/give-me-job-now/commit/66a3f591b809c2d90927c81945bc7650666df730))

- **site**: Add small gap above docs-mobile-strip in both header states
  ([`56426db`](https://github.com/dallask/give-me-job-now/commit/56426db09cc0e0f7650df4e3d20520dfaf38f33a))

- **site**: Align footer copyright and built-by lines under each other
  ([`1085bcf`](https://github.com/dallask/give-me-job-now/commit/1085bcf5145a749a50339b9948f0652c4c126299))

- **site**: Align footer icon inline before copyright text
  ([`04141ee`](https://github.com/dallask/give-me-job-now/commit/04141ee9a522e05ab29844a8861c3dca2ccfb193))

- **site**: Always center footer copyright/built-by text
  ([`2215035`](https://github.com/dallask/give-me-job-now/commit/2215035c428b6be78b03b2f36430d95157e7e9f7))

- **site**: Bump header nav link font-size to 16px
  ([`89ceba4`](https://github.com/dallask/give-me-job-now/commit/89ceba42d4a3f01395fb6dd9c124ac9350d08950))

- **site**: Cap DaisyUI tooltip bubble width to viewport (mobile horizontal-scroll source)
  ([`0fb68a3`](https://github.com/dallask/give-me-job-now/commit/0fb68a32145a0f6ef9dd113b12c3c6dd67fa9296))

- **site**: Center footer content on mobile, move copyright icon under text
  ([`ca411de`](https://github.com/dallask/give-me-job-now/commit/ca411de0dbe1bc738fc13c8e628323053567cc2c))

- **site**: Drop name from footer copyright line
  ([`a1a77ba`](https://github.com/dallask/give-me-job-now/commit/a1a77ba20b02615d7480534f2f4e2842b5ab4884))

- **site**: Fix distorted back-to-top button shape, make it emerald
  ([`0a67a23`](https://github.com/dallask/give-me-job-now/commit/0a67a23c1b98d5cd69c84158af0e1c5dc4df4a2c))

- **site**: Footer copyright — "All rights reserved. All wrongs regretted."
  ([`b829739`](https://github.com/dallask/give-me-job-now/commit/b8297393cf32dd7460ec424605c0a0af0e902dcc))

- **site**: Force footer mobile centering to override DaisyUI's grid defaults
  ([`af0aac8`](https://github.com/dallask/give-me-job-now/commit/af0aac8c43c9cd3f03fca77dc2298139918da881))

- **site**: Increase vertical space under footer icon on mobile
  ([`3b212f6`](https://github.com/dallask/give-me-job-now/commit/3b212f66213078aa3f1250ab878f9d2cf61b4766))

- **site**: Justify-content center on .footer for mobile
  ([`87200b0`](https://github.com/dallask/give-me-job-now/commit/87200b0c147c931c88795a3c09187db89b8df674))

- **site**: Justify-items center on .footer for mobile
  ([`cb7849c`](https://github.com/dallask/give-me-job-now/commit/cb7849c2957fc608e244c0bc7ddc995add729ecd))

- **site**: Make "NOW!" emerald in header brand and Home hero h1
  ([`fb9cf6f`](https://github.com/dallask/give-me-job-now/commit/fb9cf6f0ab3f5319e80b0aab1a6e4e162e5c1ab2))

- **site**: Make Home hero primary CTA button emerald
  ([`85f963e`](https://github.com/dallask/give-me-job-now/commit/85f963ea9f8ea5588a67788869ff51419eb47fb1))

- **site**: Make inline code unbreakable inside docs tables for readability
  ([`7b0b18e`](https://github.com/dallask/give-me-job-now/commit/7b0b18ee8c3a9d734aa207263b3e333ac6b04659))

- **site**: Match docs.html breadcrumb-to-content spacing with about/contact
  ([`c5f455f`](https://github.com/dallask/give-me-job-now/commit/c5f455fadb8f569b42cd13db35eea8db495d4616))

- **site**: Measure docs-mobile-strip height for spacer instead of guessing
  ([`30aebe6`](https://github.com/dallask/give-me-job-now/commit/30aebe6b6f29ea590999d724ba160397b99928cb))

- **site**: Move "Unemployment Termination Squad" above h1, swap with eyebrow
  ([`dac6979`](https://github.com/dallask/give-me-job-now/commit/dac6979de505bfd737b1eedf9037c42b7db44726))

- **site**: Move footer icon above text on mobile (remove order override)
  ([`abb07c9`](https://github.com/dallask/give-me-job-now/commit/abb07c9f1208c5c0eb9cb8bdc95a72d42dbb0300))

- **site**: Nav links back to 16px, remove tooltips from hamburger/docs-toggle buttons
  ([`2777846`](https://github.com/dallask/give-me-job-now/commit/277784628170a180a103458ba90e5623acde8374))

- **site**: Navbar justify-content:space-between + auto-width start/end above 767px
  ([`fc0dde9`](https://github.com/dallask/give-me-job-now/commit/fc0dde982790a0643e98136b9d74a8f9119c38a9))

- **site**: Nudge footer icon 2px lower
  ([`1d0c9ba`](https://github.com/dallask/give-me-job-now/commit/1d0c9ba205620f61abe033769f5e4a0ce18e01c6))

- **site**: Reduce vertical space below breadcrumbs on docs/about/contact
  ([`ba849a0`](https://github.com/dallask/give-me-job-now/commit/ba849a0022e281261ca47195db29e276e28a6f27))

- **site**: Remove "Autonomous Job/CV Collective" line from Home hero
  ([`2a01196`](https://github.com/dallask/give-me-job-now/commit/2a01196f35e491b918ffe577a52166db7f64c94c))

- **site**: Resize footer social icons to 32x32 and widen spacing
  ([`5cf538f`](https://github.com/dallask/give-me-job-now/commit/5cf538f9132b094108dcfba620d870482649128c))

- **site**: Resize footer social icons to 36x36
  ([`1a74c7f`](https://github.com/dallask/give-me-job-now/commit/1a74c7fa4a618c2ceb7a305196efab3e664f75a6))

- **site**: Restore left-aligned footer text at sm:+, shrink nav font for 768-1024px range
  ([`955701d`](https://github.com/dallask/give-me-job-now/commit/955701d4e000c0dc177127709c0ac2d331605b4c))

- **site**: Restructure docs-mobile-strip as native sticky in full-height container
  ([`1922e16`](https://github.com/dallask/give-me-job-now/commit/1922e1681680cbe792cad37f3c5b3115373fdac8))

- **site**: Restyle header brand as "Give Me Job NOW!" with red "Give"
  ([`e6cb1dd`](https://github.com/dallask/give-me-job-now/commit/e6cb1dd71f7870c117821b84c90cd90a4540ad07))

- **site**: Restyle Home hero heading as "Give Me Job NOW!"
  ([`655c865`](https://github.com/dallask/give-me-job-now/commit/655c865d1c35f4e5bac857d428fe9eb44fb48caf))

- **site**: Scope overflow-x:hidden safety-net to body only, not html
  ([`8d6afd2`](https://github.com/dallask/give-me-job-now/commit/8d6afd24f5c054ebc2833b690dce0321e74099bf))

- **site**: Stop DaisyUI .alert grid from causing mobile horizontal scroll on docs.html
  ([`d15ad40`](https://github.com/dallask/give-me-job-now/commit/d15ad404f6a10aea3566ce3aa9f3ba19d363afcc))

- **site**: Style "Unemployment Termination Squad" to match eyebrow-text convention
  ([`4db9665`](https://github.com/dallask/give-me-job-now/commit/4db96654dfce205388c67c57d39a9e6c3a4b79c8))

- **site**: Swap footer copyright icon to provided SVG
  ([`eb5ed7a`](https://github.com/dallask/give-me-job-now/commit/eb5ed7a52384cdb6c1336a3bde7bfe6a14cbb47c))

- **site**: Swap header brand icon to provided SVG at 36x36px
  ([`259aaf2`](https://github.com/dallask/give-me-job-now/commit/259aaf2b37de2784ddcfb0f7a4e072ae31e0671b))

- **site**: Update Home hero copy with new tagline text (h1 unchanged)
  ([`358fa7a`](https://github.com/dallask/give-me-job-now/commit/358fa7a33a5148a7a24225a629a671b628972152))

- **site**: Use leading-! important syntax instead of trailing-! (Tailwind CDN compat)
  ([`da041f3`](https://github.com/dallask/give-me-job-now/commit/da041f3f7a67400d08e622897a43692771d9d6ee))

- **site**: Use position:fixed for docs-mobile-nav strip so it stays visible on scroll
  ([`cff3b4f`](https://github.com/dallask/give-me-job-now/commit/cff3b4f6bf0c1ba82933d5f0ae3a9847294a385b))

- **site**: Vertically center brand logo icon and text
  ([`279e304`](https://github.com/dallask/give-me-job-now/commit/279e3046e277840b49b5c27e5380d10e042b9b58))

- **site**: Wrap long inline code snippets so they don't break mobile layout
  ([`8b944c2`](https://github.com/dallask/give-me-job-now/commit/8b944c2ab69c7e8a40495caf76ce2fb02ef9c5b3))

- **state**: Update last_updated and last_activity_desc, complete quick tasks
  ([`0c78bda`](https://github.com/dallask/give-me-job-now/commit/0c78bda65ccf5f40662479e1148a01438bada829))

- **tests**: Resolve 3 real CI failures from this session's new work
  ([`f059191`](https://github.com/dallask/give-me-job-now/commit/f05919191532ae2b9e5c45e5676ae959a5af0f75))

### Chores

- **41**: Regenerate .cursor/agents/ roster after gmj-offer-scout.md/gmj-orchestrator.md edits
  ([`1464de4`](https://github.com/dallask/give-me-job-now/commit/1464de47d6957f378933f080f2c3f5741e60c720))

- **41**: Regenerate .cursor/agents/gmj-offer-scout.md after plan 41-03's discovered_at edit
  ([`0c545ac`](https://github.com/dallask/give-me-job-now/commit/0c545aca33f6ada77016d0517102d2d6901f6198))

### Documentation

- Add DV-25 disposition to regression ledger; regenerate cursor agent mirror after phase 42 wave 2
  edits
  ([`cb14bbd`](https://github.com/dallask/give-me-job-now/commit/cb14bbd55faf81841a5543a48c0ad4ec964101ec))

- **41-04**: Document current_step seeding + wire propose_raise into gmj-orchestrator.md
  ([`275f8da`](https://github.com/dallask/give-me-job-now/commit/275f8da0844537ae5e9f892b93f7ad096aedee6d))

- **42-05**: Migrate paths-to-remove.txt glob and root/docs to output/*
  ([`ae17564`](https://github.com/dallask/give-me-job-now/commit/ae1756474849cf94f7b2c57a397175f855e37888))

- **42-05**: Migrate skill docs and schema samples to output/*
  ([`8468222`](https://github.com/dallask/give-me-job-now/commit/8468222cdc6080b15d0276bf81a47dab203c5ccb))

- **42-06**: Migrate site/docs.html and TUI dashboard notes to output/*
  ([`53347b9`](https://github.com/dallask/give-me-job-now/commit/53347b9fec9a9444bcf05de3398e3caef7215a2c))

- **43-01**: Document why rules/ stays at repo-root, not .claude/rules/
  ([`055244a`](https://github.com/dallask/give-me-job-now/commit/055244a5c8f05d40d391c89e220a5fdc836c61fe))

- **47-01**: Add cleanup wizard to docs/cli-tools.md Packaging & maintenance catalog
  ([`2e47760`](https://github.com/dallask/give-me-job-now/commit/2e47760f5da59c35b95a0f80dc3e600ed1011792))

- **47-01**: Add v6.0 requirements family subsection to docs/requirements.md
  ([`4bae621`](https://github.com/dallask/give-me-job-now/commit/4bae6216525f437f94e249394f3dcf4e862ad371))

- **47-01**: Document cleanup wizard and Phase 45 NO-GO in docs/features.md
  ([`fc2f1b1`](https://github.com/dallask/give-me-job-now/commit/fc2f1b15f5ace8335a4b66b00cd8bb7bf3fd06b9))

- **47-02**: Narrate propose_raise cap-raise retry behavior in flows.md
  ([`380325f`](https://github.com/dallask/give-me-job-now/commit/380325ff9b3f6f06874d2a93baeed9dfea0400f0))

- **47-02**: Note sources/->output/ restructure and Phase 45 NO-GO in ARCHITECTURE.md
  ([`7737f9f`](https://github.com/dallask/give-me-job-now/commit/7737f9f92347744a35da7591b9588aa015e99f95))

- **47-02**: Reference rules/README.md's repo-root placement decision in docs/rules.md
  ([`5177013`](https://github.com/dallask/give-me-job-now/commit/5177013a64179b4eea010ee2fcced7573706d7e3))

- **47-03**: Add ARCHITECTURE.md cross-link to docs/references.md
  ([`926db47`](https://github.com/dallask/give-me-job-now/commit/926db47333f0867f5f01737e48586eb23383986c))

- **47-03**: Sync gmj-sources-ingestion summary to output/* generated-content paths
  ([`c03aa44`](https://github.com/dallask/give-me-job-now/commit/c03aa440ddb078baad2e3c433ba5c36dba9c3a36))

- **47-04**: Mention gmj_cleanup_wizard.py in RUNBOOK.md Outputs section
  ([`4d308ec`](https://github.com/dallask/give-me-job-now/commit/4d308ecaef505b664986fed8f300cf1ef6bf8eae))

- **publish**: Add public assets, operator README, and manual-trigger Action
  ([`4ac01a7`](https://github.com/dallask/give-me-job-now/commit/4ac01a7586a4d3f39d3fbd4ff97461549f7ae181))

- **publish**: Clarify the publisher is visibility-agnostic
  ([`c728a95`](https://github.com/dallask/give-me-job-now/commit/c728a95f7fb1f957ba83e7f1ca1e71401af8b90e))

- **publish**: Document release.yml pipeline + PUBLIC_REPO_PAT workflow scope
  ([`24afe2a`](https://github.com/dallask/give-me-job-now/commit/24afe2a21fe083b6e04bcd5313ecb20fc56e9d61))

### Features

- Add CI workflow for pytest and update README with project details and badges
  ([`f045915`](https://github.com/dallask/give-me-job-now/commit/f0459157cbbbbfb7e61bd877bde40c77a22ab951))

- **260709-j9j**: Migrate tooltips to DaisyUI CSS-only pattern, remove Tooltipster CSS
  ([`6efecaa`](https://github.com/dallask/give-me-job-now/commit/6efecaae0db1828ad8ce7d1d6e3d40398a58282a))

- **260709-j9j**: Restyle header navbar, footer, back-to-top, docs sidebar onto DaisyUI
  ([`1d65d00`](https://github.com/dallask/give-me-job-now/commit/1d65d00e38a97f011d894a6f21d4bdada9fa42bd))

- **260709-j9j**: Restyle tables, code blocks, cards, blockquotes; add syntax highlighting
  ([`b635f57`](https://github.com/dallask/give-me-job-now/commit/b635f575aec3b0e4edc2d9eda6d9729dbfecb0d4))

- **260709-j9j**: Wire DaisyUI + highlight.js CDN, remove jQuery/Tooltipster
  ([`fc8a252`](https://github.com/dallask/give-me-job-now/commit/fc8a252297cc1affbee1c8b810a7938a812ffc65))

- **41-02**: Add deterministic ua/ru/en offer-language detector
  ([`86efb73`](https://github.com/dallask/give-me-job-now/commit/86efb735082a808a85844eeafc73aae59760d47d))

- **41-02**: Wire gmj-offer-scout to call the deterministic language detector
  ([`c20744f`](https://github.com/dallask/give-me-job-now/commit/c20744f88f9cecd993914b1df5690babce079c5f))

- **41-03**: Add discovered_at to shortlist schema and normalize drifted entries in
  gmj_merge_shortlists.py
  ([`8a1c43d`](https://github.com/dallask/give-me-job-now/commit/8a1c43d8a442d0ea1813712f861e5228f3d337bd))

- **41-03**: Pin exact shortlist entry shape and discovered_at stamping in gmj-offer-scout.md
  ([`f379d01`](https://github.com/dallask/give-me-job-now/commit/f379d01447fa92437c7dc3640063c25a25fd2371))

- **41-04**: Add propose_raise signal and failure_class to gmj_check_cap.py
  ([`791246a`](https://github.com/dallask/give-me-job-now/commit/791246a63fd643036855df3e4500a6ad254e6f99))

- **41-05**: Extract shared contact_lines() formatter into gmj_format_fields.py
  ([`6c02957`](https://github.com/dallask/give-me-job-now/commit/6c029577d361c51ffe465424119de50d6c740782))

- **42-01**: Git mv tracked softpeak pipeline output to output/artifacts/
  ([`48eeae6`](https://github.com/dallask/give-me-job-now/commit/48eeae68c76f66897f00c15151ab0964c9f2fcef))

- **42-01**: Relocate sample-offer fixtures to tests/fixtures/offers/
  ([`1607292`](https://github.com/dallask/give-me-job-now/commit/1607292b47eb3296fdc3fc5de6989fbe06c5f958))

- **42-01**: Scaffold output/* directories and relocate untracked artifacts
  ([`a126ac2`](https://github.com/dallask/give-me-job-now/commit/a126ac2ce6919accf07fce2f46835139522bde5d))

- **42-02**: Migrate cleanup-report and freeze-offer default output paths to output/
  ([`dc8cafe`](https://github.com/dallask/give-me-job-now/commit/dc8cafe44b99599b5b9139f3a579f1820233fdc2))

- **42-03**: Migrate gmj_dashboard_model.py offers_dir to output/offers/, rename paired fixture dir
  ([`bcd16f1`](https://github.com/dallask/give-me-job-now/commit/bcd16f1947c7cdf041b3652a191f96ed35e0cb8d))

- **42-04**: Migrate agent prompts from sources/* to output/* write-target paths
  ([`7f515cd`](https://github.com/dallask/give-me-job-now/commit/7f515cd81f3ea53c90464e2f36fdc58dea0def40))

- **42-04**: Migrate gmj-collective/gmj-interview commands + lockstep test to output/*
  ([`01250d7`](https://github.com/dallask/give-me-job-now/commit/01250d785d1a05aac3e7096d11722a30c36471cc))

- **42-07**: Rebuild gmj-core/ payload mirror from fully-migrated source tree
  ([`a3981c4`](https://github.com/dallask/give-me-job-now/commit/a3981c40b0266f8ad4a771e4aae639d5e9bec121))

- **44-01**: Implement gmj_cleanup_wizard.py interactive cleanup tool
  ([`d936419`](https://github.com/dallask/give-me-job-now/commit/d93641993e802bcbccfaf54ee3b507455bd17a87))

- **46-01**: Scaffold web/ Next.js App Router project
  ([`f6d4b50`](https://github.com/dallask/give-me-job-now/commit/f6d4b5002443eb51c0bdb899acf01a145d09f947))

- **46-02**: Add useHeaderScrollState + useDropdown shared hooks
  ([`253e969`](https://github.com/dallask/give-me-job-now/commit/253e96905873767523274f7644d943ef689c79fb))

- **publish**: Add gmj_bootstrap_releases.py milestone release backfill script
  ([`7178675`](https://github.com/dallask/give-me-job-now/commit/71786758ddda522e364ef416fa73b97410c0d1a9))

- **publish**: Add milestone-releases.yaml release backfill data
  ([`677d7a4`](https://github.com/dallask/give-me-job-now/commit/677d7a4f9f9647105bdb249273b71722e64829ae))

- **publish**: Add pyproject.toml + scripts/publish/requirements.txt for semantic-release
  ([`37586d6`](https://github.com/dallask/give-me-job-now/commit/37586d681eae9aba1a4feb930dd73c263b5c37f8))

- **publish**: Add release.yml semantic-release CI for the public mirror
  ([`c4de1b8`](https://github.com/dallask/give-me-job-now/commit/c4de1b824cce8c219f4421b35d73ee42f1550d08))

- **publish**: Exclude .gitleaks.toml from mirror, read it from REPO_ROOT
  ([`15f59ba`](https://github.com/dallask/give-me-job-now/commit/15f59bab416317684a6a976cc4d80f49171d867d))

- **publish**: Exclude public-assets/, TUI/, Presentation/ from mirror
  ([`14f2c85`](https://github.com/dallask/give-me-job-now/commit/14f2c8553915267c714aeabc1f96587c71f370f3))

- **quick-260709-idf**: Mobile collapsible sticky dropdown for docs sidebar
  ([`fd522a0`](https://github.com/dallask/give-me-job-now/commit/fd522a0c55880cd14bc290f86d5c60cb12151965))

- **quick-260709-idf**: Site-wide floating back-to-top button
  ([`05b57a6`](https://github.com/dallask/give-me-job-now/commit/05b57a630ad97a36cdb71d2809151c0bcd8ab83f))

- **quick-260709-ijl**: Add copy-to-clipboard buttons on fenced code blocks
  ([`88d7338`](https://github.com/dallask/give-me-job-now/commit/88d73381dd49d7ec564ceb407ecc09001adfdba1))

- **quick-260709-ijl**: Add table zebra-stripe + header background CSS
  ([`1926a07`](https://github.com/dallask/give-me-job-now/commit/1926a07d54a70b89822444dd967c34dd175d3eaf))

- **quick-260709-ijl**: Colorize inline code tags to emerald-400 in docs.html
  ([`dc1cc19`](https://github.com/dallask/give-me-job-now/commit/dc1cc1900a334921869022ef6e5c6bceb4c5ebda))

- **quick-260709-ir7**: Docs-nav-active scroll-spy style for docs.html sidebar
  ([`d49105d`](https://github.com/dallask/give-me-job-now/commit/d49105d93c03fa90e44504184e2950c90c420077))

- **quick-260709-ir7**: In-body icon insertions across docs.html with Tooltipster tooltips
  ([`2c1c66b`](https://github.com/dallask/give-me-job-now/commit/2c1c66ba51f99052f9537e707f0f478aa923906f))

- **quick-260709-ir7**: JQuery+Tooltipster CDN wiring, header nav icons, icon-only-control tooltips
  ([`1cc1056`](https://github.com/dallask/give-me-job-now/commit/1cc105621783ae9f7a8b719f8dfa72ac49bdc61f))

- **quick-260709-ir7**: Smooth transitions, header scroll hide/show, docs-strip sync, Tooltipster
  init
  ([`9c722a9`](https://github.com/dallask/give-me-job-now/commit/9c722a901b254d1c5630eeeedd036e936fa3ef85))

- **quick-260709-kig**: Add emerald section dividers between docs.html sections
  ([`e002b9f`](https://github.com/dallask/give-me-job-now/commit/e002b9f8ff3abdd9f54d42bc914583aae9f68a27))

- **quick-260709-kig**: Add file-tree icons to docs.html sidebar links
  ([`0104a6e`](https://github.com/dallask/give-me-job-now/commit/0104a6ebe987da4986d5359e84446df9ddad0531))

- **quick-260709-kig**: Extend inline-SVG icons + tooltips to 5 docs.html sections and status
  markers
  ([`7d0b348`](https://github.com/dallask/give-me-job-now/commit/7d0b348f0d5038f2ed106160347c6d96bd0efb62))

- **quick-260709-kig**: Redesign sitewide footer to DaisyUI footer-with-copyright-and-social-icons
  ([`2b1d53d`](https://github.com/dallask/give-me-job-now/commit/2b1d53d6a1db79d95edbc41e979f6249061fe241))

- **quick-260709-kig**: Restyle Home hero to DaisyUI centered-hero pattern
  ([`b1c3d29`](https://github.com/dallask/give-me-job-now/commit/b1c3d29e03448309a285f0b9d1c7e0a0ba1d1bf5))

- **quick-260709-kig**: Wrap docs.html tables in bordered-panel container
  ([`02b4f9b`](https://github.com/dallask/give-me-job-now/commit/02b4f9bf6b0126df181b44ce7416b86f38e2e785))

- **site**: Add static GitHub Pages site (Home/Docs/About/Contact) + publish workflow
  ([`4b07f5c`](https://github.com/dallask/give-me-job-now/commit/4b07f5c0b59b8407377e565ea52b675ae190acd5))

### Testing

- **41-01**: Add fixture-drift guard test; close PIPE-06 as documented no-go
  ([`19f86d9`](https://github.com/dallask/give-me-job-now/commit/19f86d9d5c9fee39bb9f38dcd66fdd0599913e0f))

- **41-03**: Add discovered_at + defensive-normalization behavior tests for gmj_merge_shortlists.py
  ([`c09e8f1`](https://github.com/dallask/give-me-job-now/commit/c09e8f1ca87938d0abea6f519b61f16501370de7))

- **41-04**: Add failing tests for propose_raise + failure_class in gmj_check_cap.py
  ([`0afb944`](https://github.com/dallask/give-me-job-now/commit/0afb94452458f86f05b5e0e1c6413447dfaa6039))

- **41-06**: Add parametrized template x backend photo/leak/section sweep
  ([`7bdb450`](https://github.com/dallask/give-me-job-now/commit/7bdb45074adb29ecbdbcb55a93c6578c2c73fd6a))

- **42-06**: Migrate opaque test-string constants and fixture data to output/*
  ([`b024fc0`](https://github.com/dallask/give-me-job-now/commit/b024fc028be033491a9cb6c3d3d3e07c2b39797a))

- **44-01**: Add failing RED tests for gmj_cleanup_wizard.py
  ([`88dae47`](https://github.com/dallask/give-me-job-now/commit/88dae47bd52f3091fbe27304c0e13bfac1a05cc8))


## v5.0.0 (2026-07-09)

### Documentation

- Update documentation regarding new features
  ([`fd2795f`](https://github.com/dallask/give-me-job-now/commit/fd2795f2f5ff47ad2a83475c658ddf5a1389fb7b))

### Features

- **publish**: Add sanitize-and-mirror publisher orchestrator + committed lists
  ([`c25ed36`](https://github.com/dallask/give-me-job-now/commit/c25ed36b6e68d7774d4c6e3eb72531d299723ee7))


## v4.0.0 (2026-07-08)

### Bug Fixes

- **260707-o8y**: Rebind anthony.html skills+contact to candidate.expertise/nested contact
  ([`4eb8983`](https://github.com/dallask/give-me-job-now/commit/4eb89831849fe5d4415d202b8e48badd0b348adc))

- **260707-o8y**: Rebind emerald.html skills+contact to candidate.expertise/nested contact
  ([`faf751e`](https://github.com/dallask/give-me-job-now/commit/faf751eb28f8c6ee8e44573c48c8c2458fd396ba))

- **260707-o8y**: Rebind enhancv-left.html skills+contact+lang to current schema
  ([`f476955`](https://github.com/dallask/give-me-job-now/commit/f47695554fca3bbe5f1fca64ab0c78a328043bc1))

- **32**: Correct gmj_record_gate.py flags in docs; root remaining hardcoded paths
  ([`394336c`](https://github.com/dallask/give-me-job-now/commit/394336ca96699def1361f01aa86c56f262dbb997))

- **32**: Document per-artifact-type render dispatch in generate.md (WR-08)
  ([`a3cdfe2`](https://github.com/dallask/give-me-job-now/commit/a3cdfe25dd82c5c6b1adc885333c2e5cfe8a1cc9))

- **32**: Rebuild gmj-core payload census after gmj_pipeline_run.py addition
  ([`28330ed`](https://github.com/dallask/give-me-job-now/commit/28330edc66e0a3dbace05919f5f21c185d651795))

- **32**: WR-01 thread configurable pipeline-dir/GMJ_PIPELINE_DIR root into per-step command docs
  and hub persona
  ([`5a2726b`](https://github.com/dallask/give-me-job-now/commit/5a2726b4daf8bb687f58229b1dde1abe11010eab))

- **32**: WR-02 document mid-render-crash HTML-sibling outcome in ARTF-02 contract
  ([`d991bdc`](https://github.com/dallask/give-me-job-now/commit/d991bdc6e407963e5768f761adf544c9e2d16ff3))

- **32**: WR-03 (continued) root remaining diagram paths in ARCHITECTURE.md
  ([`7baaa7a`](https://github.com/dallask/give-me-job-now/commit/7baaa7a7acd10625be777f39e92e4c3ba5c21549))

- **32**: WR-03 thread pipeline-dir/GMJ_PIPELINE_DIR root into ARCHITECTURE.md
  ([`faa79d1`](https://github.com/dallask/give-me-job-now/commit/faa79d1f1b16acb1cfc9429b2e390e18bf987dd6))

- **32**: WR-03 thread pipeline-dir/GMJ_PIPELINE_DIR root into gmj-cv-generator.md
  ([`298a49b`](https://github.com/dallask/give-me-job-now/commit/298a49b2fcb44c8a3c4a073fa7c4d87a51cf4b26))

- **32-06**: Drop --no-template from Draft-mode cv render invocation
  ([`24d7bd7`](https://github.com/dallask/give-me-job-now/commit/24d7bd7e09bee8436da8ede96bda8527586f7d44))

- **32-06**: Rename bare render_cv.py to gmj_render_cv.py in assertion message
  ([`1a87b40`](https://github.com/dallask/give-me-job-now/commit/1a87b40dbd80424c4f72d9d29f837484208ef4c7))

- **32-06**: Unwrap "never a single collapsed boolean" onto one line
  ([`8d1197b`](https://github.com/dallask/give-me-job-now/commit/8d1197b0230de30d78b954735b2dad408db04d51))

- **33**: WR-01 guard resolve()/is_file() against OSError and ValueError in config_file_text and
  doc_file_text
  ([`9b9be1a`](https://github.com/dallask/give-me-job-now/commit/9b9be1a641273cef8e99d45447f4c80bf10c4ce9))

- **33**: WR-02 add resolve()-based symlink-escape and NUL-byte regression tests
  ([`19451b0`](https://github.com/dallask/give-me-job-now/commit/19451b05b7978e86cb20175764ecba4c75b3bee9))

- **35**: CR-01/WR-02 make manifest read-modify-write genuinely concurrency-safe
  ([`ca2c137`](https://github.com/dallask/give-me-job-now/commit/ca2c137628c866ebf4a28fb5d43b646b692b0397))

- **35**: Single-source offer-status vocabulary; rebuild gmj-core payload
  ([`5e85207`](https://github.com/dallask/give-me-job-now/commit/5e8520762e0325c2beeb3a0e5a4c735d549171c2))

- **35**: WR-01 dispatch-cap falls back to a default when max_parallel_offers is absent
  ([`79ad4a9`](https://github.com/dallask/give-me-job-now/commit/79ad4a9b7439c4049a152854d92265ac62915a28))

- **35**: WR-03 lock manifest write in _cmd_init and unique-name _seed_state temp file
  ([`2c79f6a`](https://github.com/dallask/give-me-job-now/commit/2c79f6a00d37961d6f2595788ae7e58a0946a1b4))

- **36**: CR-01 allow path-prefixed basename refs in cleanup regex
  ([`c64adcc`](https://github.com/dallask/give-me-job-now/commit/c64adcca8486b21bd55d360a7f9f483aa8b6876a))

- **36**: CR-02 inline manifest helpers to drop excluded sibling import
  ([`0069da3`](https://github.com/dallask/give-me-job-now/commit/0069da32835db6f314568e4fbb1a194dce67e752))

- **36**: CR-02 rebuild gmj-core payload after inlining manifest helpers
  ([`abb6003`](https://github.com/dallask/give-me-job-now/commit/abb60032f4e4f504ef8e6111dbd4ef87e351fc28))

- **36**: Rebuild gmj-core payload after WR-01/WR-02 source changes
  ([`c55e47f`](https://github.com/dallask/give-me-job-now/commit/c55e47fa7e6645e89fc761f3ff34734bb3262f75))

- **36**: WR-01 add .html/.css/.tcss/.txt to cleanup SEARCH_EXTS
  ([`c44bdb3`](https://github.com/dallask/give-me-job-now/commit/c44bdb38c5c1ba0cc9e8fad59982e2ffe672ec97))

- **36**: WR-02 stop treating markdown headings as comment lines
  ([`9f210bd`](https://github.com/dallask/give-me-job-now/commit/9f210bd6f953e2c195daa3e1b54dafb0744b1e3f))

- **36**: WR-03 add regression test for path-prefixed reference detection
  ([`492de1d`](https://github.com/dallask/give-me-job-now/commit/492de1dc1733ea1ccb532fe88931206f4e4c1e76))

- **36**: WR-04 add payload script import smoke test (CHECK 11)
  ([`0038566`](https://github.com/dallask/give-me-job-now/commit/003856636d79d426aa2a4814aead73e8e7737ed6))

- **36**: WR-05 stop treating URL-embedded basenames as references
  ([`e4af98c`](https://github.com/dallask/give-me-job-now/commit/e4af98cdcb754cd00584d89eb739fb51e258048e))

- **37**: CR-01 add -- option-terminator to git clone in install.sh
  ([`f87b7a3`](https://github.com/dallask/give-me-job-now/commit/f87b7a36a9c4684594af7a652f739cb9757ff270))

- **37**: CR-02 refuse to clone into a pre-existing symlink/file/dir
  ([`8e49d58`](https://github.com/dallask/give-me-job-now/commit/8e49d58b624f01439f607020e80ebb5835c8a138))

- **37**: WR-01 sanity-check run-in-place repo root before proceeding
  ([`d06107b`](https://github.com/dallask/give-me-job-now/commit/d06107bf5728fd74dfff06b7f749a41ae7cf206c))

- **37**: WR-02 validate GMJ_INSTALL_DIR against path traversal
  ([`03d0a32`](https://github.com/dallask/give-me-job-now/commit/03d0a3293cf1471b5b0aa011d1f53a58344b9075))

- **37**: WR-03 document install.sh's fresh-clone curl|bash mode
  ([`0b5b2b3`](https://github.com/dallask/give-me-job-now/commit/0b5b2b3244adb64ccd929421fdbfaa3126caad67))

- **37**: WR-04 reconcile manual pip instructions with install.sh venv rationale
  ([`91e69e5`](https://github.com/dallask/give-me-job-now/commit/91e69e5909920ac97f28ccbe3005e92c59a00097))

- **37**: WR-05 add CR-01/CR-02 regression tests to install.sh suite
  ([`a7fad66`](https://github.com/dallask/give-me-job-now/commit/a7fad66661e2de4a85504641fa9a3aa4947a222d))

- **37**: WR-06 list tests/test_gmj_install_script.py in verification section
  ([`0a5e6fa`](https://github.com/dallask/give-me-job-now/commit/0a5e6fa54322103b56f2a988e450631a1b8be751))

- **38**: CR-01 make gmj_sdk_runner.py path resolution portable across source tree and gmj-core
  payload layouts
  ([`950e499`](https://github.com/dallask/give-me-job-now/commit/950e499e73eaf541b69e4c3dbed67dfce79c7744))

- **38**: CR-02 document required scripts/contracts/requirements.txt install alongside
  scripts/runtime/requirements.txt
  ([`a756ebe`](https://github.com/dallask/give-me-job-now/commit/a756ebe87a4de2884f1b96520756d3bf5e26cf4b))

- **38**: WR-01 surface the parsed hook reason instead of a raw JSON blob in
  permissionDecisionReason
  ([`669a251`](https://github.com/dallask/give-me-job-now/commit/669a2515ef8c8d00c908fa722ca1c05bc27d75ea))

- **38**: WR-02 use isinstance(message, ResultMessage) instead of fragile type-name string matching
  ([`6963f01`](https://github.com/dallask/give-me-job-now/commit/6963f01d32d7f2438bac02f375a90a934dc18a7c))

- **38**: WR-03 guard validate_envelope() against non-dict structured_output instead of leaking an
  AttributeError traceback
  ([`b2c5ddf`](https://github.com/dallask/give-me-job-now/commit/b2c5ddfbf0e85c7d94658fbe39ecc5c1702cabba))

- **38**: WR-04 raise on unexpected non-zero, non-2 hook exit codes instead of silently allowing
  ([`e50a600`](https://github.com/dallask/give-me-job-now/commit/e50a600a2e48999b1fdfecc12f8fc6c0eb5b213f))

- **38**: WR-05 add SDK-installed guard and bounded timeout to the live-subprocess test
  ([`f3f50ed`](https://github.com/dallask/give-me-job-now/commit/f3f50eda760fbcdf5d88ce2cd3b4f637f3ddd6db))

- **38**: WR-06 add regression tests for hook-deny-reason parsing, non-dict envelope rejection, and
  unexpected-exit-code hard-stop
  ([`af11c10`](https://github.com/dallask/give-me-job-now/commit/af11c10bd89e6f4e1d5bb551c87590667ecc1334))

- **38**: WR-07 add regression test exercising the gmj-core/ payload copy's flat-layout path
  resolution
  ([`2cea378`](https://github.com/dallask/give-me-job-now/commit/2cea3788382b3642205dc358612b6d3d8525356b))

- **38**: WR-08 add scripts/runtime/requirements.txt to gmj-core payload build
  ([`a7c8beb`](https://github.com/dallask/give-me-job-now/commit/a7c8beb1cef1a4aceeffd5415abd575e7fbb1ca4))

- **39**: CR-01 only prune generator-owned stale .cursor/agents/*.md files
  ([`b05668f`](https://github.com/dallask/give-me-job-now/commit/b05668f30bfc8d5fa7d5bcb8f5e6e6d416b23025))

- **39**: WR-01 prune stale .cursor/agents/*.md files with no matching source
  ([`f19cfc6`](https://github.com/dallask/give-me-job-now/commit/f19cfc62f16529888d9990c6d898dcad2173dc69))

- **39**: WR-02 add test asserting checked-in .cursor/agents/*.md match fresh regeneration
  ([`97ae502`](https://github.com/dallask/give-me-job-now/commit/97ae502fc05fb5165aff06394964a059fffac565))

- **39**: WR-03 normalize CRLF line endings before frontmatter parsing
  ([`54c2934`](https://github.com/dallask/give-me-job-now/commit/54c29343a5b539dd290937818b4714e12df524fc))

- **39**: WR-04 collect per-file parse failures instead of aborting whole batch
  ([`bd6cdc9`](https://github.com/dallask/give-me-job-now/commit/bd6cdc9f0913ba00bf7f050c29de151a1c6c333c))

- **39**: WR-05 warn to stderr on unexpected model field value
  ([`d712723`](https://github.com/dallask/give-me-job-now/commit/d7127234e140f45dd97a28b752b7b7afb399396f))

- **39**: WR-06 add prune-path test coverage (removal + non-generated-file safety)
  ([`7e79360`](https://github.com/dallask/give-me-job-now/commit/7e793606f6eadfcc525725cd6c439d145de744c9))

### Chores

- Migrate GSD from vendored in-repo copy to global install
  ([`227d561`](https://github.com/dallask/give-me-job-now/commit/227d5615039a0d7a3f101786b76c099c41146de6))

- **35-02**: Rebuild gmj-core payload — census-complete for gmj_dispatch_cap.py
  ([`9d54cf9`](https://github.com/dallask/give-me-job-now/commit/9d54cf96cab497eb03af4ca7c869822dbd61ba3c))

- **38-02**: Rebuild gmj-core payload census for the SDK runtime adapter
  ([`74ccbfc`](https://github.com/dallask/give-me-job-now/commit/74ccbfc0c5be340f8755a30f13adf901be71df04))

### Documentation

- **260707-nqe**: Document baxter.html as default in docstring and help
  ([`e279acf`](https://github.com/dallask/give-me-job-now/commit/e279acfea88d199ce55bfd3728dbc5d9b5b80216))

- **32-02**: Document HTML-produced vs degraded agent_result_v1 note
  ([`4da8419`](https://github.com/dallask/give-me-job-now/commit/4da8419439a10cf16b3a365c777721a7c1d9a63a))

- **32-03**: Document --artifact-types + per-type derivation in gmj-pipeline-run
  ([`60bafe8`](https://github.com/dallask/give-me-job-now/commit/60bafe8714100b6aa210460e079c050f91295cd1))

- **32-04**: Note per-type run_id derivation in the five thin-wrapper docs
  ([`d5b5ea2`](https://github.com/dallask/give-me-job-now/commit/d5b5ea2cfe8fb861f7577f735ddd0a7e4023a38d))

- **32-04**: Rewire hub persona control loop for per-artifact-type state isolation
  ([`65b5ebd`](https://github.com/dallask/give-me-job-now/commit/65b5ebde02689381e0308a3738b84b5ad43a5251))

- **32-05**: Sync ARCHITECTURE.md §5.1 with per-artifact-type state isolation
  ([`a776d8a`](https://github.com/dallask/give-me-job-now/commit/a776d8adb2a2ab7f01ddba732968881bf062618c))

- **35-05**: Document bounded concurrent-offer dispatch in gmj-orchestrator.md
  ([`e10d7dd`](https://github.com/dallask/give-me-job-now/commit/e10d7dd75f26b3e6fbb07743fbf76bf0b6bcc4e9))

- **35-05**: Rewrite gmj-batch.md step 4 for bounded concurrent dispatch
  ([`dafcae0`](https://github.com/dallask/give-me-job-now/commit/dafcae02ded77cefff95bef0bf4e13e11f61e9ba))

- **36-02**: Add cleanup-report tool discoverability + rebuild gmj-core payload
  ([`c30b064`](https://github.com/dallask/give-me-job-now/commit/c30b06451463ef708fc03536fe01e638198ad381))

- **37-02**: Document one-script installer + 4-file Python deps
  ([`3a561ec`](https://github.com/dallask/give-me-job-now/commit/3a561ec1c8b56d8125f3711b76465bdc35f53791))

- **39**: CR-01 document stale-file prune safety guarantee in README
  ([`31c486d`](https://github.com/dallask/give-me-job-now/commit/31c486d4bf604d25603b0ca41699baab32ec6ca6))

### Features

- Update candidate profile and preferences
  ([`1e3e713`](https://github.com/dallask/give-me-job-now/commit/1e3e713af63205d658d58bf71721b5c26395b267))

- **260707-nqe**: Default to baxter.html with graceful ReportLab fallback
  ([`4efabdc`](https://github.com/dallask/give-me-job-now/commit/4efabdc27da8c800120c636e9667b30d05db307e))

- **32-01**: Implement --artifact-types resolver / run_id deriver
  ([`78d5a1d`](https://github.com/dallask/give-me-job-now/commit/78d5a1dc0cefd021c7eb681e9e3b164723eefd56))

- **33-01**: Implement docs_files() and doc_file_text() model methods
  ([`b2fbb71`](https://github.com/dallask/give-me-job-now/commit/b2fbb715af94da2ac2d24d2d5441c996f999e02f))

- **33-02**: Add DocFileModal, docs TabPane, and widget seeding
  ([`0b42816`](https://github.com/dallask/give-me-job-now/commit/0b4281678aa8aa1c80402d888daa71426d8d579f))

- **33-02**: Style the docs tab/modal in .tcss + fix tab_labels regression
  ([`2b2039a`](https://github.com/dallask/give-me-job-now/commit/2b2039aa60bd39b032345853868a53176a264320))

- **33-03**: Wire _apply_docs, poll dispatch, and docs-table row-selection open
  ([`371dc93`](https://github.com/dallask/give-me-job-now/commit/371dc93ffba017848ea2614c15c80764cd9277e2))

- **35-01**: Add max_parallel_offers field + rename manifest status vocabulary
  ([`4774799`](https://github.com/dallask/give-me-job-now/commit/477479941411a479d484fafa29cf5d69e5a94438))

- **35-01**: Concurrency-safe manifest writes + status vocabulary rename
  ([`ed31ffb`](https://github.com/dallask/give-me-job-now/commit/ed31ffb29a767ce3f4b0afcd164ea0e331c340fa))

- **35-01**: Freeze --max-parallel-offers on init + fixture rename to new vocabulary
  ([`1aae463`](https://github.com/dallask/give-me-job-now/commit/1aae463093c3488c4d911b1998235c9e6537a98d))

- **35-02**: Gmj_dispatch_cap.py — deterministic offer-level dispatch-cap query
  ([`592af3e`](https://github.com/dallask/give-me-job-now/commit/592af3e79e4c5c6d28692a2d63162031d5fbc89a))

- **35-03**: _batch_rollup() gains by_offer_status worst-case aggregate
  ([`6a6d474`](https://github.com/dallask/give-me-job-now/commit/6a6d474abc0b87f8fc1912a71a543375c51061ef))

- **35-04**: Add 4 concurrency-era status-* theme variable keys
  ([`5ef15ec`](https://github.com/dallask/give-me-job-now/commit/5ef15ecf2c8810eff632018b0c5b6a044a7004b0))

- **35-04**: Render by_offer_status breakdown in _apply_vacancies()
  ([`1826cd9`](https://github.com/dallask/give-me-job-now/commit/1826cd993698c5869211f4d413fc5dfdcc8973cd))

- **36-01**: Implement gmj_cleanup_report to turn RED contract GREEN
  ([`0bebee2`](https://github.com/dallask/give-me-job-now/commit/0bebee2450cbec3d718f600b9340cf4fdd92894e))

- **37-01**: Implement gmj-core/bin/install.sh (GREEN)
  ([`ba5cc2f`](https://github.com/dallask/give-me-job-now/commit/ba5cc2f1749e356c50614469a9b2f7b68c6983a6))

- **38-01**: Build scripts/runtime/gmj_sdk_runner.py + isolated requirements.txt
  ([`dc99d44`](https://github.com/dallask/give-me-job-now/commit/dc99d448872a9689acabde4a2f128d629124cff7))

- **38-02**: Add HOOK-PARITY.md and README.md for SDK runtime adapter
  ([`a0a7765`](https://github.com/dallask/give-me-job-now/commit/a0a7765dd36cbafd594418e28cf9cae9d9b74f43))

- **39-01**: Build EXPERIMENTAL Cursor roster generator
  ([`bf79f0d`](https://github.com/dallask/give-me-job-now/commit/bf79f0d3793559517fff0c6e22ad92f4921381b3))

- **39-02**: Generate real .cursor/agents/*.md roster + adapter README
  ([`a8c8f9d`](https://github.com/dallask/give-me-job-now/commit/a8c8f9d04c663d07aa7662977385a85bc2261447))

### Testing

- **32-01**: Add failing test for artifact-type resolver / run_id deriver
  ([`0d070b7`](https://github.com/dallask/give-me-job-now/commit/0d070b7a8a0f011263c1dc59b772c4ff1ac70131))

- **32-02**: Add ARTF-02 regression test for CV render HTML-sibling guarantee
  ([`3849c21`](https://github.com/dallask/give-me-job-now/commit/3849c21a1f7e32671f3219c078ba967e0dc58e7e))

- **32-03**: Prove per-artifact-type state.json gate isolation
  ([`ecefc18`](https://github.com/dallask/give-me-job-now/commit/ecefc18b7df2884391282d086fc0736560d2f441))

- **32-05**: Lock per-type state isolation + --artifact-types doc as regression guards
  ([`204469a`](https://github.com/dallask/give-me-job-now/commit/204469a95f5455d1ee681ae8d0673725848cfe64))

- **32-06**: Regression-lock the actual documented Draft-mode invocation
  ([`895fdde`](https://github.com/dallask/give-me-job-now/commit/895fddeab84cf18bafaef9dc7f0ec32292c29192))

- **33-01**: Add failing test for docs_files/doc_file_text model methods
  ([`5aae87e`](https://github.com/dallask/give-me-job-now/commit/5aae87e57b094babe4329d921cac744c8af513f8))

- **33-01**: Regression-proof docs_files missing-dir degrade + snapshot key shape
  ([`97488ca`](https://github.com/dallask/give-me-job-now/commit/97488ca57778d9b64a9cbb96b67b6afc2e55b8a0))

- **33-03**: Regression-test docs-table drill-in, fresh-read, and empty-state
  ([`07608fb`](https://github.com/dallask/give-me-job-now/commit/07608fb6acc3297357e84e9deb683c9219048a0e))

- **35-02**: Dispatch-cap decision regression suite — 7/7 green
  ([`b9ad060`](https://github.com/dallask/give-me-job-now/commit/b9ad0600d1400db9cef6f11ef98cd05b56648e09))

- **35-03**: By_offer_status regression coverage in test_gmj_runs.py
  ([`20424a9`](https://github.com/dallask/give-me-job-now/commit/20424a9ceae830b529040edb9ce3d813363abca9))

- **35-04**: Assert by_offer_status breakdown renders in #vac-batches
  ([`288fc04`](https://github.com/dallask/give-me-job-now/commit/288fc044d37a1be309a7d6306561de3aebf0ef5b))

- **35-05**: CONC-06 doc-wiring regression assertions
  ([`5146229`](https://github.com/dallask/give-me-job-now/commit/51462295219877901cf043f365dc5bbc3e2bcfc4))

- **36-01**: Add failing test contract for gmj_cleanup_report
  ([`aab1aaf`](https://github.com/dallask/give-me-job-now/commit/aab1aaf3a68f8a38bd4a57fcc45347b442cf7c05))

- **37-01**: Add failing test for gmj-core/bin/install.sh (RED)
  ([`cb10e45`](https://github.com/dallask/give-me-job-now/commit/cb10e45c945e2ff5f94e3b0e51ce2cd90f79c7c8))

- **38-01**: Add and pass automated test suite for the SDK runtime adapter
  ([`0b22f9f`](https://github.com/dallask/give-me-job-now/commit/0b22f9f84e12c7e5741f287873f67fc8ec846282))

- **39-01**: Add 9-test suite for the Cursor roster generator
  ([`2154a7f`](https://github.com/dallask/give-me-job-now/commit/2154a7f183bcaa9ae06db2a6f5bf1a2a1e9d4a52))

- **39-02**: CURSOR-HOOK-PARITY.md gap checklist + 5 new adapter tests (14 total)
  ([`cfddfb4`](https://github.com/dallask/give-me-job-now/commit/cfddfb4df51b8a555eff74b1970561ce2df9bbc4))


## v3.1.0 (2026-07-07)

### Bug Fixes

- **25**: Comment no longer trips rebrand grep0 (bare pipeline-run → PIPELINE_RUN ref); rebuild
  payload
  ([`ba59173`](https://github.com/dallask/give-me-job-now/commit/ba59173db53d8ea607ab84defd741e97288b03bc))

- **26**: IN-01 IN-02 dedupe repo-default warning copy + broaden resolve guard to ValueError
  ([`60be12d`](https://github.com/dallask/give-me-job-now/commit/60be12d646c21057ae8c49c3d2cb84c7cec6ebb6))

- **26**: WR-01 make manage confirm workers exclusive to prevent stacked modals + double-write
  ([`0a3e1e1`](https://github.com/dallask/give-me-job-now/commit/0a3e1e17d2317f8a5679b9444ff5d49f5286851a))

- **26**: WR-02 latch SAFE-02 confirm-once only after a successful write
  ([`9d3cdad`](https://github.com/dallask/give-me-job-now/commit/9d3cdada4bbc0de9e5ae413c2996ba55174c5450))

- **26-01**: Revert pipeline config to safe defaults (SAFE-01)
  ([`9eaf85a`](https://github.com/dallask/give-me-job-now/commit/9eaf85a7f4bd505db91f9ddff7ba58494da39f48))

- **27**: WR-01 absolutize dashboard --pipeline-dir once so board and launched child agree
  ([`2746f8a`](https://github.com/dallask/give-me-job-now/commit/2746f8a0d49c2b6e237f3ca833d805bcc5191573))

- **27**: WR-02 resolve gmj_merge_shortlists pipeline root lazily in main, not at import
  ([`132e5bd`](https://github.com/dallask/give-me-job-now/commit/132e5bdf235f1353d4386704552a38eb1087f62b))

- **27**: WR-03 drop unused Path import in gmj_pipeline_paths resolver module
  ([`1ffb7e2`](https://github.com/dallask/give-me-job-now/commit/1ffb7e2a8fb36057e6520d9fc981a584825f1e5d))

- **28**: IN-01 walk launches/ once per snapshot and thread into both surfaces
  ([`33391e7`](https://github.com/dallask/give-me-job-now/commit/33391e7d8440ba8ae11e359803931bd9c2ccd762))

- **28**: IN-02 clean up orphan .tmp when atomic replace fails
  ([`0229f33`](https://github.com/dallask/give-me-job-now/commit/0229f33d2ac27953bc2caf1430060a527f2a859d))

- **28**: WR-01 best-effort launch sidecar write keeps spawned child tracked
  ([`ff07d3c`](https://github.com/dallask/give-me-job-now/commit/ff07d3cc35038a0d81fe77cfb0abf311b7c5564d))

- **28**: WR-02/WR-03 bounded launch-sidecar staleness cap
  ([`d4f7e0b`](https://github.com/dallask/give-me-job-now/commit/d4f7e0bc59abe3cac1e7c6d067fdd2e51a142eb4))

- **29**: IN-02 migrate sibling render probes to _settle on real conditions
  ([`4139f8a`](https://github.com/dallask/give-me-job-now/commit/4139f8a9a9a3c9610f9a9fbe13427615414a9075))

- **29**: WR-01 settle TEST-01 layout probe on real seeding+layout condition
  ([`ea904d1`](https://github.com/dallask/give-me-job-now/commit/ea904d10ad8a3f5e71b22b21a8e08cb8adfb2e9c))

- **30**: Correct cli-tools native/renamed script classification (WR-01: check_claims renamed,
  native 11->13)
  ([`92b0567`](https://github.com/dallask/give-me-job-now/commit/92b05673aae4559dbd57721a5e336be80e361984))

### Chores

- **30-02**: DOCS-04 regenerate gmj-core payload + manifest
  ([`76bcbec`](https://github.com/dallask/give-me-job-now/commit/76bcbec5bf5272628e054fa1e0fecf9aabd91181))

### Documentation

- **27-01**: Orchestrator prose honors operator pipeline root
  ([`e8cc031`](https://github.com/dallask/give-me-job-now/commit/e8cc0313c1745723b8868fc7f2908b4d5891384f))

- **30-01**: DOCS-01 refresh cli-tools catalog + gmj-dashboard behavior
  ([`77f9e7e`](https://github.com/dallask/give-me-job-now/commit/77f9e7e5400d25d6cbe97e0bf87344091d57685d))

- **30-01**: DOCS-02 author TUI/testing-plan.md from UAT handoff
  ([`15b09e4`](https://github.com/dallask/give-me-job-now/commit/15b09e449ade752b422d650736d69b43469cefb6))

- **30-01**: DOCS-03 mark FIND-07 run-verb typo RESOLVED
  ([`531ba96`](https://github.com/dallask/give-me-job-now/commit/531ba96faf48e9d48fd02ba50b8cad97deee3b20))

- **31-02**: Author docs/DEMO-WALKTHROUGH.md + index both new docs
  ([`f157635`](https://github.com/dallask/give-me-job-now/commit/f157635d292e1035ae6b709844a902e4725b16d1))

- **31-02**: Author docs/SHOWCASE.md end-to-end narrative
  ([`454b5a7`](https://github.com/dallask/give-me-job-now/commit/454b5a795ba014b0c7d6832a129605749e3d1a5e))

### Features

- CURSOR enhance dashboard features with new config file browsing and offer detail capabilities
  ([`1c2bbab`](https://github.com/dallask/give-me-job-now/commit/1c2bbab5d2f8435774eef5e40ed2191e73b09050))

- **26-02**: Gate first repo-default config write behind confirm seam (SAFE-02)
  ([`63d632c`](https://github.com/dallask/give-me-job-now/commit/63d632ca9155163ee3a34204a80ad28ad3c17704))

- **26-02**: Persistent repo-default warning banner under --manage (SAFE-02a)
  ([`97d0157`](https://github.com/dallask/give-me-job-now/commit/97d0157f448bb3afc687bb0b564c1c5317a230f0))

- **27-01**: Add shared resolve_pipeline_dir single-source resolver
  ([`e2abe15`](https://github.com/dallask/give-me-job-now/commit/e2abe153256af60058501a362e1ed5e4f0296e49))

- **27-01**: Swap self-defaulting pipeline roots to shared resolver
  ([`c528160`](https://github.com/dallask/give-me-job-now/commit/c528160a634db245cec74e0bd6a71e6d26519df2))

- **27-02**: Carry pipeline-dir into child via GMJ_PIPELINE_DIR env + prompt token
  ([`3cefcd6`](https://github.com/dallask/give-me-job-now/commit/3cefcd66f26f957ed9277cf8466b8382f63b6f6e))

- **27-02**: Thread self._pipeline_dir through all three launch handlers
  ([`38b09b5`](https://github.com/dallask/give-me-job-now/commit/38b09b514c9f3e582115738fe0be3459fd545098))

- **27-03**: Add frozen-vs-live legend to #commands panel (HON-03)
  ([`0b7aeb5`](https://github.com/dallask/give-me-job-now/commit/0b7aeb57fc42a1a8857e3cbc88c96016b69f4132))

- **28-01**: Add clean reaper + bounded dead-pid prune (RELOAD-02)
  ([`dd6cb17`](https://github.com/dallask/give-me-job-now/commit/dd6cb171d3fe8f9a2f969ae9929c703d3beab99d))

- **28-01**: Add launch-sidecar writer + safe id generator (RELOAD-01)
  ([`c76f4c6`](https://github.com/dallask/give-me-job-now/commit/c76f4c6fb306c1219c4a19fc15926abad26d7023))

- **28-02**: Add read-only _is_pid_alive + _launches liveness reader
  ([`dfad126`](https://github.com/dallask/give-me-job-now/commit/dfad126a9722240cc835ed5a17e94a9ab78f5a6f))

- **28-02**: Fold launches into pipeline_activity() + snapshot()
  ([`957b767`](https://github.com/dallask/give-me-job-now/commit/957b767cc666bfdc4dfa679c4c0e328013075cd6))

- **28-03**: Reap sidecar on child exit + heartbeat recovery parity
  ([`9ae592b`](https://github.com/dallask/give-me-job-now/commit/9ae592b9e197fff2001819feace140b1e66d8183))

- **28-03**: Write launch sidecar on feature launch + thread launch_id
  ([`5de8da2`](https://github.com/dallask/give-me-job-now/commit/5de8da26acdea2044081bfae73aada60e21ed7bf))

### Testing

- **26-01**: Add pipeline config safe-default regression guard (SAFE-01)
  ([`f3a482f`](https://github.com/dallask/give-me-job-now/commit/f3a482f5846d258aa9744bbca539316da4333c1b))

- **27-01**: Add failing resolver test for pipeline-dir resolution
  ([`95d38fb`](https://github.com/dallask/give-me-job-now/commit/95d38fb686d293de7f4bc7f7d361c7eaa7a69bf8))

- **27-02**: Add failing tests for pipeline-dir prompt token + child env carrier
  ([`89650c4`](https://github.com/dallask/give-me-job-now/commit/89650c4ac57b4747e419fa77017da00763bcfdca))

- **27-02**: HON-02 Pilot assertion — prompt arg + child env carry the operator dir
  ([`776023c`](https://github.com/dallask/give-me-job-now/commit/776023c5a697eedbdeaf01e0da2b2b0eb37088c2))

- **28**: Cover launch-sidecar staleness cap (WR-02/WR-03)
  ([`5cdc8de`](https://github.com/dallask/give-me-job-now/commit/5cdc8de4a6dd084bc698c9ceae29393ad750f36e))

- **28-01**: Add failing tests for launch-sidecar writer + safe id
  ([`f1dd57e`](https://github.com/dallask/give-me-job-now/commit/f1dd57e99a3a3adb96ab251a9b8f6a71606586bf))

- **28-01**: Add failing tests for reaper + bounded dead-pid prune
  ([`27371e7`](https://github.com/dallask/give-me-job-now/commit/27371e76a514c7321aadc462e6ba551cb64ca8c8))

- **28-02**: Add failing _is_pid_alive + _launches liveness tests
  ([`fc70747`](https://github.com/dallask/give-me-job-now/commit/fc707477f1eef1ac944e3438283968d91baf3d03))

- **28-02**: Add failing reload-simulation + launches-surface tests
  ([`13bb1dd`](https://github.com/dallask/give-me-job-now/commit/13bb1ddac72721aba3261f277e9d16341e0807d2))

- **28-03**: Add failing tests for launch-sidecar write + slash-derived kind
  ([`854d3f0`](https://github.com/dallask/give-me-job-now/commit/854d3f0e2c61bd597c0e15493f6bb07b07f03a16))

- **28-03**: Add failing tests for reap-on-exit + heartbeat recovery parity
  ([`afc71d0`](https://github.com/dallask/give-me-job-now/commit/afc71d0a3a7ff3da90e5e8f4b39129c359cc5415))

- **29-01**: Add shared _settle bounded poll-until-predicate helper
  ([`96272d0`](https://github.com/dallask/give-me-job-now/commit/96272d08aaaaf5ba4bd65cd8bd431ebe16b7ac98))

- **29-01**: Retrofit 9 flaky render-settle tests onto _settle (TEST-04)
  ([`8833d73`](https://github.com/dallask/give-me-job-now/commit/8833d73f410fad411bf17a6fa1bc5c56888bba4f))

- **29-02**: Add long-candidate layout min-height coverage (TEST-01)
  ([`5feef99`](https://github.com/dallask/give-me-job-now/commit/5feef99522aa7980cf268d81a3a3bc3f043055c4))

- **29-02**: Add real two-step batch-modal Escape-cancel coverage (TEST-02)
  ([`09abc90`](https://github.com/dallask/give-me-job-now/commit/09abc9097e0e8f7166c4cec9d23539a4ec153956))

- **29-02**: Settle three fixed-pause render probes flagged under load
  ([`7bc0efe`](https://github.com/dallask/give-me-job-now/commit/7bc0efe8970082e620f697f3ce5e818d78f895e3))

- **29-03**: Add deterministic in-flight overlay test (TEST-03)
  ([`bee90c0`](https://github.com/dallask/give-me-job-now/commit/bee90c0c3b703e3e3ab14365651c36b57c376db9))


## v3.0.0 (2026-07-05)

### Bug Fixes

- Resolve REMOVED-FILES.md at archived phase-dir path post-cleanup
  ([`eb53ba5`](https://github.com/dallask/give-me-job-now/commit/eb53ba5356cd13ab75305103a2667e0c77612c9d))

- **22-03**: Read batch completed-count by exclusion to keep grep-guard green
  ([`19bc943`](https://github.com/dallask/give-me-job-now/commit/19bc9433590992b38c6c73820462d5eddaceae78))

### Documentation

- **25-03**: Add Dashboard flow section to flows.md (PKG-03)
  ([`51110ce`](https://github.com/dallask/give-me-job-now/commit/51110ceb816e53faa9a370eba6925319fe90b95e))

- **25-03**: Catalog scripts/dashboard/ in cli-tools + fix counts (PKG-03)
  ([`057390d`](https://github.com/dallask/give-me-job-now/commit/057390d75b0f22249843fbc9e9bb703a2c638c59))

- **25-03**: Document /gmj-dashboard in commands.md (PKG-03)
  ([`e0cc3ba`](https://github.com/dallask/give-me-job-now/commit/e0cc3ba64db9791369fd682c3f30d78ce158c793))

### Features

- **20-01**: Implement gmj_dashboard_model core — import seam + torn-read tolerance (GREEN)
  ([`e7c5b26`](https://github.com/dallask/give-me-job-now/commit/e7c5b26517455c3c197a8a7f064fed633127cd5e))

- **20-02**: Domain metric aggregation builder (MODEL-04)
  ([`8719de9`](https://github.com/dallask/give-me-job-now/commit/8719de978962ed1213374f3c17904771b0227acf))

- **20-02**: Thin readers + stages.dag + run_detail + main/--json (MODEL-05, MODEL-01 finalize)
  ([`e4ceebf`](https://github.com/dallask/give-me-job-now/commit/e4ceebfea0e16b9d29a67ffe14a4b040936df1eb))

- **21-01**: GmjDashboard read-only Textual app skeleton + btop tcss
  ([`5de3e3a`](https://github.com/dallask/give-me-job-now/commit/5de3e3a6bb0ec6fc4eccbdea4af3bb0b74f032d7))

- **21-02**: Runs DataTable seeding + guard-safe status cell + targeted _apply_runs diff
  ([`420cb08`](https://github.com/dallask/give-me-job-now/commit/420cb08d3c7b6392685f76396cb478d3401cd5d9))

- **21-03**: Metrics panel + throughput sparkline + candidate/config panels
  ([`546d35e`](https://github.com/dallask/give-me-job-now/commit/546d35e99a1ed9481c3bd6fe214345d8dd9ca8af))

- **21-03**: VIEW-05/06 tests + full Phase-21 suite gate
  ([`e382312`](https://github.com/dallask/give-me-job-now/commit/e382312357349360c478678fd97663aba49a2961))

- **22-01**: Render DAG stage strip into #dag-placeholder, colored from projection
  ([`cd8964f`](https://github.com/dallask/give-me-job-now/commit/cd8964fae63ee81431985e0c80a044e55d795044))

- **22-02**: Pilot test for run drill-in modal (VIEW-09)
  ([`2c3c640`](https://github.com/dallask/give-me-job-now/commit/2c3c6401130e3fa9ead093f982c9e099b7f071e6))

- **22-02**: RunDetailModal drill-in wired to on-demand run_detail
  ([`315df67`](https://github.com/dallask/give-me-job-now/commit/315df67b57f41abcfcd827563112e37d948104bf))

- **22-03**: Render vacancies + batch rollup into #vac-placeholder
  ([`171e19b`](https://github.com/dallask/give-me-job-now/commit/171e19bc62ee529d39463fea5029479129bce0e8))

- **22-04**: Filter Input + persistent _apply_runs predicate; keep built-in palette
  ([`e07d9c7`](https://github.com/dallask/give-me-job-now/commit/e07d9c7db67b6604823d6cc54f4bc93b4af07102))

- **22-04**: Pilot tests — ctrl+p opens palette; filter narrows runs table
  ([`9e1baee`](https://github.com/dallask/give-me-job-now/commit/9e1baeea3b014cfe7d1b70098655db215352f9a5))

- **23-01**: Activity() builder + activity snapshot key
  ([`472d0b5`](https://github.com/dallask/give-me-job-now/commit/472d0b58aa186a8e2000322692fd6cabb8cfc39c))

- **23-01**: Failures() builder + errors snapshot key + throughput_by_status
  ([`44e1ab6`](https://github.com/dallask/give-me-job-now/commit/44e1ab64eb2043bf1ba51bde594633de27cb32ff))

- **23-02**: Commands (VIEW-15) + debug (VIEW-16) panels
  ([`a83e7ef`](https://github.com/dallask/give-me-job-now/commit/a83e7ef768cbff9265a58fc21134ea10c9fe4065))

- **23-02**: Errors panel (VIEW-12) — red-forward Gate A/Gate B detail
  ([`bf806e3`](https://github.com/dallask/give-me-job-now/commit/bf806e389ea862df259902e947ba508c4279e952))

- **23-02**: Grid + theme scaffold for the five max-density panels
  ([`4b96d83`](https://github.com/dallask/give-me-job-now/commit/4b96d83ca4e9b8ce305c1b78cbbf3fb954ace90a))

- **23-03**: Activity feed panel — newest-first event timeline (VIEW-13)
  ([`6daa7d3`](https://github.com/dallask/give-me-job-now/commit/6daa7d33f21b708960ce00f8474e25c7522857ff))

- **23-03**: Extended charts panel — block graph + Gate A/B bars + per-status trend (VIEW-14)
  ([`2bdfd24`](https://github.com/dallask/give-me-job-now/commit/2bdfd24acab2ce69bd510b26050e0cca1931cd71))

- **24-01**: Add launcher seam, batch orchestrator, config line-rewrite
  ([`5e98a96`](https://github.com/dallask/give-me-job-now/commit/5e98a96f43f6c4ac335f34d7e98b490f88050ddc))

- **24-01**: Unit + integration + SAFETY-01 negative tests for actions
  ([`f77ece4`](https://github.com/dallask/give-me-job-now/commit/f77ece48fe4eb4a2feea7020f49e5382b04460d9))

- **24-02**: Launch/resume/batch action methods with never-silent feedback
  ([`55f0c27`](https://github.com/dallask/give-me-job-now/commit/55f0c27bcaf9349fc823239cdade0e8f1e3eeb97))

- **24-02**: Seam attrs + --manage binds real actions + config handlers (m/c)
  ([`f154839`](https://github.com/dallask/give-me-job-now/commit/f154839066266b439026b5734d05f9119a2ebbd9))

- **25-01**: Add /gmj-dashboard read-only command doc (PKG-01)
  ([`7dd4938`](https://github.com/dallask/give-me-job-now/commit/7dd49389333331639d282134ccbc6862cce8a822))

- **25-01**: Pin textual>=6.1,<7 for dashboard (PKG-02)
  ([`9e66bf1`](https://github.com/dallask/give-me-job-now/commit/9e66bf11934f11b3d0d77c3062fa9d31cce74e2d))

- **25-02**: Rebuild gmj-core payload — mirror dashboard + sha256 manifest (closes D-20-1)
  ([`73c4830`](https://github.com/dallask/give-me-job-now/commit/73c483084cb25cc1ebb303d3b45dba2ed6f0bb30))

- **25-02**: Ship dashboard .tcss + requirements.txt in census_payload()
  ([`9297df1`](https://github.com/dallask/give-me-job-now/commit/9297df1d260b6bcff5225cf1edea4dc8e33915b5))

### Testing

- **20-01**: Add failing core test for gmj_dashboard_model (RED)
  ([`337d5d8`](https://github.com/dallask/give-me-job-now/commit/337d5d8331ea41e88604b76cbf6320412327d5f5))

- **20-02**: Add failing metric-aggregation assertions (MODEL-04)
  ([`c6b9089`](https://github.com/dallask/give-me-job-now/commit/c6b908931169c009351191ca8244ef90e3e363fc))

- **20-02**: Add failing thin-reader / run_detail / invariant tests (MODEL-05 + MODEL-01)
  ([`a77f5de`](https://github.com/dallask/give-me-job-now/commit/a77f5decae940871d54164d4e57a7801c53e22d7))

- **21-01**: Add Pilot harness + VIEW-01/02/04/07 + SAFETY-02 tests
  ([`bf08cbe`](https://github.com/dallask/give-me-job-now/commit/bf08cbe38c1f7113f3b4d1e0366032721494b2a1))

- **21-02**: VIEW-03 runs table rows + status label text + targeted-update stability
  ([`b943ad0`](https://github.com/dallask/give-me-job-now/commit/b943ad0792e2402762d6f71eb437c60e76fd436e))

- **22-01**: Pilot test proves DAG strip renders tokens + colors gates (VIEW-08)
  ([`76068a7`](https://github.com/dallask/give-me-job-now/commit/76068a7a929835759c05354ca4ea5aef9ba13dbe))

- **22-03**: Pilot test — vacancies rows + batch delivered/total render
  ([`7020539`](https://github.com/dallask/give-me-job-now/commit/70205395ad8e9d629510cc1200e9a6f320fc1934))

- **23-01**: Add enriched Gate A/B fail gate fixtures
  ([`5c680ba`](https://github.com/dallask/give-me-job-now/commit/5c680ba48bfc14574bef4e962ae889276d841af1))

- **23-01**: Add failing tests for activity() builder
  ([`2c4de6a`](https://github.com/dallask/give-me-job-now/commit/2c4de6ad8259366eed060e2e2ee1681d41e1130b))

- **23-01**: Add failing tests for failures() + throughput_by_status
  ([`4b3b962`](https://github.com/dallask/give-me-job-now/commit/4b3b96241914f8009937dfa7de529943d3f5b435))

- **23-02**: Add failing commands + debug panel Pilot tests (RED)
  ([`015d527`](https://github.com/dallask/give-me-job-now/commit/015d527729fafea87c06b0823705eadcacd0693d))

- **23-02**: Add failing errors panel Pilot test (RED)
  ([`bd5ec13`](https://github.com/dallask/give-me-job-now/commit/bd5ec131dcbade078e4a2d47cd19c00edeedcec5))

- **23-03**: Add failing test_activity_panel_renders for the activity feed (VIEW-13)
  ([`0d3e130`](https://github.com/dallask/give-me-job-now/commit/0d3e130a5a7cd7ccebc4dea75c28a6887f65bc27))

- **23-03**: Add failing test_charts_panel_renders for extended charts (VIEW-14)
  ([`4cdaaa4`](https://github.com/dallask/give-me-job-now/commit/4cdaaa4582e0588ce3dda959b02f639b77b690ea))

- **24-02**: Pilot + AST tests — manage binds real actions, launch/failure, MANAGE-06 no-write
  ([`6f93160`](https://github.com/dallask/give-me-job-now/commit/6f93160b5eff05584b8c2960fa168de0cd4a7c1c))

- **25-01**: Assert dashboard textual pin floor+cap, no transitive render (PKG-02)
  ([`57a8d6d`](https://github.com/dallask/give-me-job-now/commit/57a8d6d3f871f1100b71bf3f93d953876f4f5bc1))


## v2.0.0 (2026-07-05)

### Bug Fixes

- Propagate P9 candidate-schema rename to shipped live-path payloads
  ([`5759274`](https://github.com/dallask/give-me-job-now/commit/5759274281e996a5dd96d148db4e973c1cb573ce))

- **09**: WR-01 wire _contact_lines to CONTACT registry constants
  ([`8582792`](https://github.com/dallask/give-me-job-now/commit/858279232c5da01975244510cf9e9c9fc61ba419))

- **09**: WR-02 assert registry consumption via AST in single-owner gate
  ([`415ae78`](https://github.com/dallask/give-me-job-now/commit/415ae7873a0668fe134110699b442163b6e67256))

- **09**: WR-03 type-guard source_span to degrade without traceback
  ([`c6bda8c`](https://github.com/dallask/give-me-job-now/commit/c6bda8ceb1f8bda20115a5084195ee430700c2a1))

- **09**: WR-04 remove dead Contact section; WR-05 render role_progression
  ([`3838f71`](https://github.com/dallask/give-me-job-now/commit/3838f71922105666e73847850c8a5dd1e6a1dd46))

- **10**: WR-01 strip any scheme in _norm_site to match hook url_host
  ([`4c827ef`](https://github.com/dallask/give-me-job-now/commit/4c827ef51e7aff24dac7db9c35c2cf32e392c8d0))

- **10**: WR-02 assert fail-closed marker and no OK sentinel in missing-sources test
  ([`05a72a9`](https://github.com/dallask/give-me-job-now/commit/05a72a9dd45d075331176a7e392d16ed1e417ec4))

- **10**: WR-03 scope gmj-interview Write/Bash grants to exclude candidate.yaml + assert in contract
  test
  ([`d5d4b99`](https://github.com/dallask/give-me-job-now/commit/d5d4b99dcb0562914d2f7dac853576dad4776287))

- **10**: WR-04 add root additionalProperties:false so misspelled scope key is rejected
  ([`1f0752e`](https://github.com/dallask/give-me-job-now/commit/1f0752edb4d4bc961053b929c93a623587c570b3))

- **11**: CR-01 reject NaN/Infinity on merge load and emit
  ([`c1824b0`](https://github.com/dallask/give-me-job-now/commit/c1824b0de54fdad3667d04c8a79b3e299973271f))

- **11**: WR-01 keep distinct same-host offers from dedup-collapsing
  ([`9cb5001`](https://github.com/dallask/give-me-job-now/commit/9cb5001ac45d6c4db3ed3f1ea24038d508c0f9c5))

- **11**: WR-02 validate merge output against shortlist schema before write
  ([`0174211`](https://github.com/dallask/give-me-job-now/commit/01742111388735464a781aaee03c67e9113b3353))

- **11**: WR-03 test --out path-traversal containment rejection
  ([`42fcd71`](https://github.com/dallask/give-me-job-now/commit/42fcd713bd83399f6d319083016d39c2b8be14e5))

- **11**: WR-04 test dual-shape board loader (bare list, stdin, error path)
  ([`b7f3d64`](https://github.com/dallask/give-me-job-now/commit/b7f3d648ac39b4e619c7d50bc44dd344d41843f8))

- **11**: WR-05 correct preferences load comment to match exit-1 behavior
  ([`babcc43`](https://github.com/dallask/give-me-job-now/commit/babcc43995b7d816d91bc899ee202f95cf2ac3ae))

- **11**: WR-06 fail closed with non-zero exit on missing sources.yaml
  ([`3634154`](https://github.com/dallask/give-me-job-now/commit/3634154ed9951b78c680c55361a0bc9071552ec1))

- **12**: CR-01 require delivered label AND gate pass in resume predicate
  ([`5d7ab5f`](https://github.com/dallask/give-me-job-now/commit/5d7ab5f8c7eee44a3e55e4d2e622100e38ba0004))

- **12**: WR-01 reject non-finite JSON literals on load in gmj_batch
  ([`9018a8a`](https://github.com/dallask/give-me-job-now/commit/9018a8a40abeca6a5285fb1c87be5260e2357943))

- **12**: WR-02 seed run state in one atomic in-process write
  ([`2aaf65d`](https://github.com/dallask/give-me-job-now/commit/2aaf65d1c95c5dae2e74bd8f9b07849ac0100226))

- **13**: WR-01 render deterministic SVG achievement marker instead of emoji
  ([`1b351ec`](https://github.com/dallask/give-me-job-now/commit/1b351ec48a7701a96d5c0a56ccf23460b4c1abcd))

- **13**: WR-02 scan leak-prone HTML attribute values in template lint
  ([`9f324fc`](https://github.com/dallask/give-me-job-now/commit/9f324fc07df66018cfcda2c12eba3958986ec4be))

- **13**: WR-03 assert real multi-page reflow in longer-than-sample test
  ([`02f6ab4`](https://github.com/dallask/give-me-job-now/commit/02f6ab4d13267f01906fe2f4f53656289935c58b))

- **14**: WR-01 assert exact offending_claims set in invented-number truth test
  ([`613a7f7`](https://github.com/dallask/give-me-job-now/commit/613a7f77451fd9609bdc1c1754c8fe1789708a8f))

- **14**: WR-02 reject whitespace-only-text claim in loader to honor no-drop contract
  ([`2786ae9`](https://github.com/dallask/give-me-job-now/commit/2786ae923d99db8d3c76a3a93ce96dbe716a4309))

- **15**: WR-01 add reverse-direction orphan ledger check
  ([`f258f99`](https://github.com/dallask/give-me-job-now/commit/f258f99249e572f840783053bf6e36eabcd59082))

- **15**: WR-02 slice deferred section to next heading generically
  ([`a048672`](https://github.com/dallask/give-me-job-now/commit/a048672afff17ddcebed3f512fd75ec4bcfa89ab))

- **15**: WR-03 key completeness on disposition rows not prose
  ([`416e731`](https://github.com/dallask/give-me-job-now/commit/416e73126f5a8d820e215fc6aba1dd9e60405f4a))

- **16**: CR-01 coerce nullable manifest fields in batch inspect table mode to avoid TypeError
  traceback
  ([`bcf509d`](https://github.com/dallask/give-me-job-now/commit/bcf509d5eb563cf3782fda8672963066e7b32c19))

- **16**: WR-01 add status key to healthy batch rows for uniform batches list schema
  ([`1bd4ef2`](https://github.com/dallask/give-me-job-now/commit/1bd4ef2db265b2ac29223e36aa2dd91cb9374c40))

- **16**: WR-02 extend read-only invariant test to all four subcommands and assert no new files
  ([`b2f3447`](https://github.com/dallask/give-me-job-now/commit/b2f344728d0267cea28fa23adfcdb54969b12827))

- **16**: WR-03 add ordering tie-break test for runs sharing an id-timestamp key
  ([`a881206`](https://github.com/dallask/give-me-job-now/commit/a8812064f6d595ab1e62281a87cddf1d29fc2ecd))

- **16**: WR-04 add batch inspect table-mode degrade and hashseed determinism tests
  ([`e092e48`](https://github.com/dallask/give-me-job-now/commit/e092e48753347554bc87584ee45a5b48cc7db575))

- **17**: CR-01 stage content rewrites after git mv in --apply
  ([`5017cf7`](https://github.com/dallask/give-me-job-now/commit/5017cf7d813cebb1f52aee6e14db33e75f587602))

- **17**: WR-01 enforce framework_globs deny-list in the rename guard
  ([`05ec9a5`](https://github.com/dallask/give-me-job-now/commit/05ec9a57ff6df77d87db4f7e34124fe742e66b13))

- **17**: WR-02 prune framework files from the reference-rewrite walk
  ([`bc625ac`](https://github.com/dallask/give-me-job-now/commit/bc625ac5b5e033ea8bebffac857eb0fd62d9da5b))

- **17**: WR-03 preserve alias in import <stem> as <alias> rewrite
  ([`e79ad24`](https://github.com/dallask/give-me-job-now/commit/e79ad24a4ec14e941ca54b08f422c98036f00a04))

- **17**: WR-06 reject traversal/absolute git mv destinations
  ([`a2a8880`](https://github.com/dallask/give-me-job-now/commit/a2a88804ff1807aa381380da8a52d05dd05177dc))

- **17-05**: Apply command-content rewrites left unstaged by git-mv rename
  ([`326bebc`](https://github.com/dallask/give-me-job-now/commit/326bebcdc908241b117d4a4ee8b01d3939f12718))

- **18**: CR-01 ship fonts, requirements.txt, templates in payload + harden blind tests
  ([`e00610d`](https://github.com/dallask/give-me-job-now/commit/e00610d655ac5a7cd717e761de6cc7814adeb2be))

- **18**: Self-exclude vendored gmj-core manifest copy from rebrand grep
  ([`cbbf6e5`](https://github.com/dallask/give-me-job-now/commit/cbbf6e56002bba258914d350276ce71d04641763))

- **18**: WR-01 make payload manifest reproducible across rebuilds
  ([`6cf511a`](https://github.com/dallask/give-me-job-now/commit/6cf511a29dcfc3955c85a525934e14fd36bfbc3d))

- **18**: WR-02 verify shipped sha256 hashes at install time
  ([`3cde99e`](https://github.com/dallask/give-me-job-now/commit/3cde99eccad3f893ad6b661ad9a24ae920da506d))

- **18**: WR-03 preserve a user's own gmj-named hook on install
  ([`7cd3d4b`](https://github.com/dallask/give-me-job-now/commit/7cd3d4ba84bf39dc810d199f314363a9467f2b70))

- **18**: WR-04 surface a non-object settings.json hooks value instead of clobbering it
  ([`afa2ec8`](https://github.com/dallask/give-me-job-now/commit/afa2ec8ce36e33a52b579da2731712cd7375ac61))

- **19**: IN-02 require README section index entries to be real links + exist
  ([`2c4a385`](https://github.com/dallask/give-me-job-now/commit/2c4a3852062c7b5782bc5a907d5c6a31983c37af))

- **19**: IN-03 tolerate optional title in README .md link regex
  ([`8bde9f7`](https://github.com/dallask/give-me-job-now/commit/8bde9f7d77b1e8dc9c8f3a5e99132d25365fc8cf))

- **19**: IN-04 add trailing word-boundary guard to GMJ_CMD
  ([`0e3a389`](https://github.com/dallask/give-me-job-now/commit/0e3a3896e5f91ac1e2652a6940046438db68a40e))

- **19**: WR-01 scope HTML-comment historical allowance to closed block
  ([`27d4701`](https://github.com/dallask/give-me-job-now/commit/27d4701aad2fbbc1a91a2b997d71ed0dea966021))

- **19**: WR-02 make test_every_docs_skill_exists non-vacuous
  ([`419b592`](https://github.com/dallask/give-me-job-now/commit/419b592bfd3ce4051e231957f5602f0b6b2121f4))

- **19**: WR-03 require explicit inline marker for per-line historical allowance
  ([`34d030e`](https://github.com/dallask/give-me-job-now/commit/34d030ed3ea7f5b27c05999036766f8eb8883280))

- **hooks**: Scope validate-envelope to subagent's final message
  ([`f4ccaa9`](https://github.com/dallask/give-me-job-now/commit/f4ccaa9c99946b7e1661118314bb132454352af5))

- **quick-260703-t8o**: Compact sparse source-span list indices in render bridge
  ([`8226d93`](https://github.com/dallask/give-me-job-now/commit/8226d93926132f154c8e850dd84122de5b53e372))

### Chores

- **13-01**: Pin PyMuPDF and weasyprint in requirements.txt
  ([`3564344`](https://github.com/dallask/give-me-job-now/commit/356434495a183c6c866b8cf0e142ab875d90c2ed))

- **18-05**: Remove legacy example/ prototype + __pycache__ (STRUCT-01)
  ([`809f888`](https://github.com/dallask/give-me-job-now/commit/809f8886f6f08f629410fb7780cbb3c803fcac0a))

### Documentation

- **08-04**: Add RUNBOOK for end-to-end real-offer run
  ([`7db416d`](https://github.com/dallask/give-me-job-now/commit/7db416d04ce8f9423d7ae4199332033a45f478e2))

- **09-03**: Align composer/configurator prose to new schema grammar
  ([`ff3f565`](https://github.com/dallask/give-me-job-now/commit/ff3f565e9eb95370e44918e28bfaa00f22dee70d))

- **09-03**: Migrate candidate-yaml-schema skill to new schema grammar
  ([`581567a`](https://github.com/dallask/give-me-job-now/commit/581567af5b6cc80d0d61e1e1ab787b1c5350ac40))

- **09-04**: Bridge assembles complete headers from span-traced claims
  ([`8be61fd`](https://github.com/dallask/give-me-job-now/commit/8be61fd899179f36f0fefab43bbcf9bc2bd5848d))

- **13-05**: Retarget cv-generator handoff to gmj-template-creator + document by-name slug render
  ([`8c21c6b`](https://github.com/dallask/give-me-job-now/commit/8c21c6bbac80c54b4eb7625f4e8f86ac44c8266d))

- **14-04**: Worked quantified-framing examples in truth/fit rubrics
  ([`4204718`](https://github.com/dallask/give-me-job-now/commit/4204718e72c48922add1d2d668f560e1beb51574))

- **14-05**: Document Phase-15 scored-eval fixtures (not boolean gates)
  ([`c6526e1`](https://github.com/dallask/give-me-job-now/commit/c6526e12d231f3068b8456759a260e905134e882))

- **18-04**: Refresh .claude/CLAUDE.md architecture to gmj- roster
  ([`e6b2d12`](https://github.com/dallask/give-me-job-now/commit/e6b2d122706f7f3d63463a6a42073ef7df575a3c))

- **18-04**: Refresh root CLAUDE.md to current gmj- roster
  ([`4a001dc`](https://github.com/dallask/give-me-job-now/commit/4a001dca7072a712b4399b3e9fedf2127350b0a2))

- **19-02**: Reconcile ARCHITECTURE roster to nine agents
  ([`2c0183d`](https://github.com/dallask/give-me-job-now/commit/2c0183d144a91039e79e4e9c29187074876a9a39))

- **19-02**: Reconcile stale legacy agent names in source files
  ([`7f0817a`](https://github.com/dallask/give-me-job-now/commit/7f0817a1bdbf46629b79dccd7bcd9214cc92fe88))

- **19-04**: Author docs/agents.md — 9-agent gmj- roster
  ([`68e80aa`](https://github.com/dallask/give-me-job-now/commit/68e80aaeda6331dbe09f84e85fb89bc8ad52fd84))

- **19-04**: Author docs/rules.md — Read-on-demand rules index
  ([`2f9d610`](https://github.com/dallask/give-me-job-now/commit/2f9d61050b0b7a08e87e994273b928413f4c350d))

- **19-05**: Author docs/commands.md — all 12 commands
  ([`bfbede9`](https://github.com/dallask/give-me-job-now/commit/bfbede93238b9cb686f855848158044e9d890a70))

- **19-05**: Author docs/flows.md — real end-to-end flows
  ([`5ebd192`](https://github.com/dallask/give-me-job-now/commit/5ebd1923e89aa81c2d2b97632e80376560c57f3b))

- **19-06**: Author docs/cli-tools.md — 31 gmj_*.py CLI tools grouped by dir
  ([`d03d7de`](https://github.com/dallask/give-me-job-now/commit/d03d7de21bd7ab417187f8cf59cb939d9a38eb30))

- **19-06**: Author docs/requirements.md — v2.0 milestone requirement inventory
  ([`02aa9f1`](https://github.com/dallask/give-me-job-now/commit/02aa9f12a2d8a05f71ce940553908d05b80f60be))

- **19-07**: Author docs/configuration.md — every config file with shape, schema, consumer
  ([`525f67b`](https://github.com/dallask/give-me-job-now/commit/525f67bf8849847e068902b7595c25e5e6c183cc))

- **19-07**: Author docs/skills.md — all 10 gmj- skills
  ([`532497a`](https://github.com/dallask/give-me-job-now/commit/532497aceb169a1c9797892f9388a0410416b438))

- **19-08**: Author docs/features.md — core value, guarantees, v2.0 capabilities
  ([`63a828b`](https://github.com/dallask/give-me-job-now/commit/63a828ba4afc9fa1cfff62d3b08cc2d1febdc672))

- **19-08**: Author docs/installation.md — standalone gmj-core install path
  ([`1320faf`](https://github.com/dallask/give-me-job-now/commit/1320fafe1dfbb5ae9b991dfb5965ff963867d74d))

- **19-08**: Author docs/references.md — schemas, envelope, runbook links, docs-currency pointer
  ([`8092ac4`](https://github.com/dallask/give-me-job-now/commit/8092ac44aad94e469a7970b9197b9518acb2b9ac))

- **19-09**: Author root README.md — app description + docs link index + quickstart
  ([`77a16ab`](https://github.com/dallask/give-me-job-now/commit/77a16abf62597fd26c5d1b9edb8a3d32003154ba))

- **19-09**: Genericize rebrand-manifest example old-names in configuration.md
  ([`8e68228`](https://github.com/dallask/give-me-job-now/commit/8e682284fb6bbcc98aa78ccc0c69020891d99846))

### Features

- **08-04**: Add additive draft-mode branch to cv-generator
  ([`c9fd28b`](https://github.com/dallask/give-me-job-now/commit/c9fd28bb013efb0405d78c973a089b3435405a49))

- **09-01**: Add single-owner schema_fields registry
  ([`068d32e`](https://github.com/dallask/give-me-job-now/commit/068d32e5340aede255957eb01de790fbc38099d8))

- **09-02**: Add localized 'expertise' label (en/ua/ru)
  ([`38abe1a`](https://github.com/dallask/give-me-job-now/commit/38abe1a10a8f9d1a79e416694dea7ca88bc65dce))

- **09-02**: Migrate render_cv.py to expertise schema + shape-aware contact
  ([`e84c345`](https://github.com/dallask/give-me-job-now/commit/e84c345033bcae4bea6a3f3dfbdc2aaea3864069))

- **09-02**: Reconcile .ua overlay to expertise schema + gate ua fallback
  ([`933380f`](https://github.com/dallask/give-me-job-now/commit/933380f7953bcc3bc5153ff3737bbb8149de9cad))

- **09-04**: Bridge round-trip test + migrate enhancv-inspired.html to v2.0 shape
  ([`2c6e743`](https://github.com/dallask/give-me-job-now/commit/2c6e743defe3bb3fd91b10001eb7fb58c73627e9))

- **10-01**: Add preferences.schema.json shape + committed valid preferences.yaml
  ([`256e1cc`](https://github.com/dallask/give-me-job-now/commit/256e1cc4133beb59c2d720bd07bcfef8246ef19c))

- **10-01**: Implement validate_preferences.py shape+subset fail-closed CLI
  ([`59bcc66`](https://github.com/dallask/give-me-job-now/commit/59bcc6636ce105a3722a138b7353adcdea9ff7ef))

- **10-02**: Add /gmj-interview gap-filling interviewer persona
  ([`9aa9cfd`](https://github.com/dallask/give-me-job-now/commit/9aa9cfd93b9cda31d18f432cc2b83886bd50a8ea))

- **11-01**: Deterministic merge/dedup/scope-filter/rank script + job-seeker .md
  ([`90e55c2`](https://github.com/dallask/give-me-job-now/commit/90e55c23fb4814fa0acd5a47b2ccaa4611e7c532))

- **11-01**: Freeze shortlist entry contract (schema + sample)
  ([`a43a557`](https://github.com/dallask/give-me-job-now/commit/a43a557b46ac23bcd08ffae4ffa65ca068536df1))

- **11-03**: Document hub per-board fan-out + deterministic merge invocation
  ([`a4cadde`](https://github.com/dallask/give-me-job-now/commit/a4caddecd37d03e0a5bcbc8dd7aa918fe936bd6e))

- **11-03**: Reframe offer-scout board search to one board per worker
  ([`2d9cb31`](https://github.com/dallask/give-me-job-now/commit/2d9cb310b66dcba8dc14df90793b21ba0a54efb5))

- **12-01**: Batch-manifest schema + valid sample
  ([`c4aed73`](https://github.com/dallask/give-me-job-now/commit/c4aed73a21d8878214b86c90b37f336622df9f00))

- **12-01**: Gmj_batch.py init — selection, coarse->draft, manifest, state seed (GREEN)
  ([`a27103c`](https://github.com/dallask/give-me-job-now/commit/a27103ca15f4ef74a272e71e1ef4b20b537e07bb))

- **12-02**: Gmj_batch mark/resume/record-spec subcommands (GREEN)
  ([`6c0d2da`](https://github.com/dallask/give-me-job-now/commit/6c0d2da0e09ec41a9634bc39f13aaf41a0db96d9))

- **12-03**: Add /gmj-batch hub persona for multi-select per-offer batch
  ([`57371f2`](https://github.com/dallask/give-me-job-now/commit/57371f25a53c0b99dd82cdaccd48b985237c9485))

- **13-01**: Gmj_visual_diff.py deterministic compare==ship visual diff
  ([`e6e7a2e`](https://github.com/dallask/give-me-job-now/commit/e6e7a2e9b410c132aa4cff4003cf9d6c0f917ebe))

- **13-02**: Add gmj_template_lint.py fail-closed zero-sample-strings gate
  ([`a4e34ce`](https://github.com/dallask/give-me-job-now/commit/a4e34ce90d065f640eab9ae325eaa90ce7f699bd))

- **13-03**: Add gmj-baseline branded CV template with portable @font-face
  ([`2c3287a`](https://github.com/dallask/give-me-job-now/commit/2c3287ab2d626257ad931ffcdc6932f84f29366b))

- **13-04**: Add /gmj-template persona (Task-holder loop driver)
  ([`49cbfed`](https://github.com/dallask/give-me-job-now/commit/49cbfed61d4cded287a270c9740e46d140b22197))

- **13-04**: Add gmj-template-creator spoke (vision to Jinja2, no Task)
  ([`d91cdf4`](https://github.com/dallask/give-me-job-now/commit/d91cdf49c28ae8e114f22937f9e1245aa49e8894))

- **14-01**: Group interview-prep claims by section under markdown headers
  ([`4e8052b`](https://github.com/dallask/give-me-job-now/commit/4e8052b3d6c7fb6935dd54c8cc48f1c359732006))

- **14-02**: Declare optional cover_letter_tone in preferences schema
  ([`00183ee`](https://github.com/dallask/give-me-job-now/commit/00183ee161baf936bb5c07f38d7fd43d89bf6921))

- **14-04**: Add depth guidance to artifact-composer
  ([`99598b0`](https://github.com/dallask/give-me-job-now/commit/99598b0e87ebc83c318ef3b229607ab7a6179ca9))

- **14-05**: Wire cover_letter_tone hint as a hub-passed composer param
  ([`7c254fb`](https://github.com/dallask/give-me-job-now/commit/7c254fbd346491de677b377c2dfe9901d4d7b1cc))

- **15-01**: Add advisory artifact-quality richness/tone eval
  ([`edf0d11`](https://github.com/dallask/give-me-job-now/commit/edf0d11b3e60ec964d34b528058caca4bbe2f710))

- **15-02**: Add count-agnostic completeness gate test_regression_ledger.py
  ([`c05e7a9`](https://github.com/dallask/give-me-job-now/commit/c05e7a905220595d1eedaacd12b7e662311eb884))

- **16-01**: Gmj_runs.py read-only inspector — status projection + list ops
  ([`56f7317`](https://github.com/dallask/give-me-job-now/commit/56f73174ad96b61c6fb80a10d09e00ea3b16ade9))

- **16-01**: Gmj_runs.py — run inspect / batch inspect + printed resume
  ([`3d93227`](https://github.com/dallask/give-me-job-now/commit/3d932278a409d8ae9e8db91ce38c878462f23b32))

- **16-03**: Add /gmj-runs read-only inspector persona
  ([`8f53cd2`](https://github.com/dallask/give-me-job-now/commit/8f53cd2853d760b06143fe91cd0f74001b564d9b))

- **17-01**: Author config/ownership-manifest.yaml framework|app allow-list
  ([`47ffbd4`](https://github.com/dallask/give-me-job-now/commit/47ffbd4ab99965dc5064681b8ca1554cac0fffcb))

- **17-02**: Add manifest-gated gmj_rebrand.py dry-run/apply engine
  ([`9f5d060`](https://github.com/dallask/give-me-job-now/commit/9f5d060cbc94fcba38694b30eb62ea985e20bfb5))

- **17-03**: Rename 23 app scripts to gmj_ + rewrite all inbound refs
  ([`3b3e099`](https://github.com/dallask/give-me-job-now/commit/3b3e099ccb973310fc3274be0aa437d5ffd5e114))

- **17-04**: Rename 8 agents to gmj- + atomic gate-node cluster flip
  ([`83a9918`](https://github.com/dallask/give-me-job-now/commit/83a9918b8ff5fa6076922accb59b0fa9388aaac5))

- **18-03**: Add rules/README.md index + CLAUDE.md rules-index pointer
  ([`f9faffa`](https://github.com/dallask/give-me-job-now/commit/f9faffac57bfe436f039a5996c87db79b94146f2))

- **18-03**: Add six frontmatter-scoped invariant rules under rules/
  ([`dda7d09`](https://github.com/dallask/give-me-job-now/commit/dda7d09c37531ab4e81258a5d99916bc9e85259a))

- **18-06**: Build gmj-core payload + sha256 census manifest
  ([`3d61dc5`](https://github.com/dallask/give-me-job-now/commit/3d61dc5ef5b655e49e5bee2435e938068042a02b))

- **18-07**: Author vendored zero-dep installer copy/scaffold + path containment
  ([`808e019`](https://github.com/dallask/give-me-job-now/commit/808e0194be18c003f2f552f199db87dfe84645b6))

- **18-07**: Idempotent settings.json merge (nested hooks) — install test green
  ([`0961a8a`](https://github.com/dallask/give-me-job-now/commit/0961a8a0f2fea14ab2bb62167a95f1e050f2719d))

- **18-08**: Add manifest-gated dry-run GSD-removal reporter
  ([`1385a1a`](https://github.com/dallask/give-me-job-now/commit/1385a1a7f3423a169f10bf7079cd804aec3815fe))

- **19-03**: Add docs-currency rule + index it (DOCS-04)
  ([`b0c0f92`](https://github.com/dallask/give-me-job-now/commit/b0c0f928540af94fe0b3b46b2a0e29d8b0e12a13))

- **testing**: UAT results tracker — record_uat.py + ledger + STATE.md acceptance marker
  ([`74c728d`](https://github.com/dallask/give-me-job-now/commit/74c728d3c8e4144258c0b15c23a0201d56bff1d2))

### Refactoring

- **17-05**: Rename app commands to gmj- + scope engine for dir-group command
  ([`d0e218a`](https://github.com/dallask/give-me-job-now/commit/d0e218a27f2552700b6ac26dd5a136eea47ec954))

- **17-06**: Rename 10 app skills to gmj- + rewrite all cross-refs
  ([`458a053`](https://github.com/dallask/give-me-job-now/commit/458a053953e539d4dcb0e8c3b9220891f23c760c))

- **17-07**: Rename 6 app hooks to gmj- + rewrite settings.json registrations
  ([`22e7f15`](https://github.com/dallask/give-me-job-now/commit/22e7f15c9201d756a9d4e8607accbf553682aff3))

### Testing

- **08-04**: Assert cv-generator draft wiring + runbook done-criteria
  ([`8043540`](https://github.com/dallask/give-me-job-now/commit/80435407aec208ab566fdca8532ce6bea06ed575))

- **09-01**: Add hard-gate schema migration harness (RED until renderer migrates)
  ([`2792d4e`](https://github.com/dallask/give-me-job-now/commit/2792d4e8d23116eecddf49926a8c71e5de5255e3))

- **09-04**: Migrate draft fixture to new-key spans + structural claims
  ([`1cf97d4`](https://github.com/dallask/give-me-job-now/commit/1cf97d41527f48090c3a14eb97cf3afd44ae514e))

- **10-01**: Add failing harness for validate_preferences (RED)
  ([`6d4d959`](https://github.com/dallask/give-me-job-now/commit/6d4d959baeb956df50fb62924d5a6de3500f6ddb))

- **10-02**: Add doc-lint contract for /gmj-interview persona
  ([`13df3d5`](https://github.com/dallask/give-me-job-now/commit/13df3d56a44f0c538a60465211067be6cddcca3d))

- **11-01**: Determinism/dedup/scope-filter/soft-rank/.md-wording suite
  ([`4048d51`](https://github.com/dallask/give-me-job-now/commit/4048d51cc60a5f0b48fa58b82925881b04a9ef5a))

- **11-02**: Prove scope-guard fires per worker under fan-out (SCOUT-05)
  ([`a78d3c3`](https://github.com/dallask/give-me-job-now/commit/a78d3c3d77eb2dc5e76662d4641fb088a6df9e31))

- **11-03**: Lock SCOUT-01/03 persona + hub fan-out contract via doc-lint
  ([`5e5b243`](https://github.com/dallask/give-me-job-now/commit/5e5b2434c7907627ac5297993d7b6a3da9ac0410))

- **12-01**: Failing SELECT-01/02/03 + path-traversal harness (RED)
  ([`2d24764`](https://github.com/dallask/give-me-job-now/commit/2d247649584b0c4e61f5eec1c26b61aaefc47f62))

- **12-02**: Failing SELECT-04 mark/resume + record-spec cases (RED)
  ([`1b71992`](https://github.com/dallask/give-me-job-now/commit/1b71992ed5fe119798fabdb2d4da17afce89690b))

- **12-03**: Add /gmj-batch persona doc-lint pinning SELECT-01/02 invariants
  ([`f43a88a`](https://github.com/dallask/give-me-job-now/commit/f43a88a08fd8bff80bc83f0f9d1cbcae29a615fa))

- **13-01**: Determinism + compare==ship tests for gmj_visual_diff
  ([`aa8dfac`](https://github.com/dallask/give-me-job-now/commit/aa8dfac881028ace3e96fcd77a382b874da040c4))

- **13-02**: Assert lint leak/clean/label/backstop behaviors under python3
  ([`f5381c2`](https://github.com/dallask/give-me-job-now/commit/f5381c21d1d8a57a7350e0fe9ec0bc73353f5113))

- **13-03**: Gmj-baseline render gate — by-name, Cyrillic, no-overflow
  ([`6e58d40`](https://github.com/dallask/give-me-job-now/commit/6e58d4013e9f05fe1b38cba9322045440a3c14a5))

- **13-04**: Add doc-lint for gmj-template persona + creator spoke
  ([`31daf1c`](https://github.com/dallask/give-me-job-now/commit/31daf1c39a007567d8cbb725bda1cd59f90bd592))

- **14-01**: Rich four-section fixture + section-grouping test
  ([`651b201`](https://github.com/dallask/give-me-job-now/commit/651b201339e4c1af0b5aad92176b9aa4aa824c4e))

- **14-02**: Fail-closed cover_letter_tone field test
  ([`bba08f6`](https://github.com/dallask/give-me-job-now/commit/bba08f6951d012e83cf814f84c212e3a83477ba3))

- **14-03**: Add real-metric PASS and invented-number FAIL fixtures
  ([`da2ac28`](https://github.com/dallask/give-me-job-now/commit/da2ac28fcbe0e3df84d12d9c117708fce38aa720))

- **14-03**: Assert quantified-framing PASS/FAIL pair (ARTIFACT-03)
  ([`2329ff4`](https://github.com/dallask/give-me-job-now/commit/2329ff4960099016de18a45100cdda01c0766a4e))

- **14-04**: Doc-lint for composer + rubric depth guidance
  ([`3fe23f4`](https://github.com/dallask/give-me-job-now/commit/3fe23f474d5e5a4a291b24dc728f886fb03c0916))

- **14-05**: Toned cover-letter fixture + coverage_map + gates-green test
  ([`82cb86b`](https://github.com/dallask/give-me-job-now/commit/82cb86b1e96769850c7aa60ace55024dc10806a2))

- **15-01**: Add category-split labeled set for artifact-quality eval
  ([`246645e`](https://github.com/dallask/give-me-job-now/commit/246645e17297398b5634ac349c0e2ac48857d64e))

- **16-01**: Add heterogeneous read-only fixture corpus for gmj_runs
  ([`e84245d`](https://github.com/dallask/give-me-job-now/commit/e84245de487ea1370a4358baa6cd3e4099eec87a))

- **16-02**: Add deterministic test suite for gmj_runs inspector
  ([`8903b60`](https://github.com/dallask/give-me-job-now/commit/8903b606775a3282daf2337dc649e8f0574faffa))

- **16-03**: Doc-lint /gmj-runs persona (inverts gmj-batch frontmatter assertion)
  ([`45b51a9`](https://github.com/dallask/give-me-job-now/commit/45b51a9fd3eb3e42427815d8cf82c86de8c6174d))

- **17-01**: Add tests/test_ownership_manifest.py structural gate
  ([`0b2c561`](https://github.com/dallask/give-me-job-now/commit/0b2c56154655e0d1915cdcfe30563c065ebbe975))

- **17-02**: Add rebrand-acceptance + gate-cluster-consistency gates
  ([`2ebc6f1`](https://github.com/dallask/give-me-job-now/commit/2ebc6f1bd66d67c47578cfcf2b23bdf5d4e07353))

- **18-01**: Add RED contract for STRUCT-01 structure cleanup
  ([`949c446`](https://github.com/dallask/give-me-job-now/commit/949c4461c5479454c69b07364addd1ed9105d567))

- **18-01**: Add RED contract for STRUCT-02 rules scope folder
  ([`9cb5dbe`](https://github.com/dallask/give-me-job-now/commit/9cb5dbeed3a59ff6f02d446b7dbb6a0c323d085f))

- **18-01**: Add RED contract for STRUCT-03 CLAUDE.md refresh
  ([`05fba56`](https://github.com/dallask/give-me-job-now/commit/05fba56842128fb87bf50447347fada4a83d3318))

- **18-02**: Add clean-install contract (PACKAGE-01/02, RED)
  ([`bf887cf`](https://github.com/dallask/give-me-job-now/commit/bf887cf700f3836673a4f475772fc98a3dd78577))

- **18-02**: Add GSD-removal dry-run contract (PACKAGE-03/04, RED)
  ([`8a5184a`](https://github.com/dallask/give-me-job-now/commit/8a5184a3a9892861f1e8af2eb2f501baf5f2f563))

- **19**: Lock WR-01/WR-03 historical-allowance scoping + fix block close marker
  ([`74800d3`](https://github.com/dallask/give-me-job-now/commit/74800d32d0bc747b0c8cdbeaf6b926181760ff45))

- **19-01**: Add DOCS-03 doc-currency gate (RED-first)
  ([`2d6a308`](https://github.com/dallask/give-me-job-now/commit/2d6a3087398cccf13e939e0182d8a9ab2cbd2470))

- **quick-260703-t8o**: Compaction regression test + fixture; type-mismatch gate
  ([`f3ff45a`](https://github.com/dallask/give-me-job-now/commit/f3ff45aec84969a85f2e1b845cd15fda8dbc95fa))


## v1.0.0 (2026-07-03)

- Initial Release
