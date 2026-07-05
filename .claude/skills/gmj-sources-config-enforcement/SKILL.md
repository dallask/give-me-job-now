---
name: gmj-sources-config-enforcement
description: Mandatory sources.yaml read-and-enforce protocol for the web-search spoke (gmj-offer-scout).
---

## Sources config (read first)

**Before any web search**, read `config/sources.yaml` and extract the constraint arrays:

```yaml
# config/sources.yaml — example
sites:
  - https://www.work.ua/
  - https://robota.ua/
  - https://jobs.dou.ua/
  - https://www.linkedin.com/jobs/
cities:
  - Kyiv
languages:
  - ua
  - en
```

Apply these as hard limits on every search:

| Config key | How to apply |
|---|---|
| `sites` | Strip protocol/www → use as `allowed_domains` in **every** `WebSearch` call. Never search or fetch from domains not in this list. |
| `cities` | Append city names to all search queries. Report salary/demand data scoped to these cities only. |
| `languages` | Run search queries in all listed languages. Preference results in those languages. |
| `limits.max_vacancies` | Hard cap on total vacancy files written this run (gmj-offer-scout). |
| `limits.max_search_queries` | Hard cap on total `WebSearch` calls this run. |
| `limits.max_fetches` | Hard cap on total `WebFetch` calls this run. |

**Limits enforcement:**
- Initialise counters before any tool calls: `searches_used = 0`, `fetches_used = 0`, and `vacancies_saved = 0` (gmj-offer-scout).
- Increment the relevant counter on every call.
- When a counter reaches its limit, stop issuing that call type even if more results could be found.
- If a limit was hit, record it in `notes`: `"Stopped at N/max_search_queries (limit reached)"`.
- Default limits if the key is absent: `max_search_queries = 10`, `max_fetches = 15`, `max_vacancies = 20`.

If `config/sources.yaml` is missing or unparsable, log a warning and proceed with unrestricted search — do not fail silently without noting the fallback.
