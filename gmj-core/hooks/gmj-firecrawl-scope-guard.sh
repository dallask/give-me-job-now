#!/usr/bin/env sh
# PreToolUse — enforce config/sources.yaml scope on every Bash-invoked
# scripts/offers/gmj_firecrawl_search.py call (SEARCH-07).
#
# The existing WebSearch|WebFetch matcher (gmj-sources-scope-guard.sh) cannot see a
# Bash-invoked Python script's target host — tool_input for a Bash call is only a
# `command` string, not a structured url/query field. Without this hook, any
# Firecrawl call — on or off the config/sources.yaml allow-list — would run
# unchecked, a scope-guard bypass. This hook closes that gap on the SAME `Bash`
# PreToolUse matcher gmj-block-destructive-commands.sh already uses (chained, not
# replacing).
#
# Contract:
#   - read stdin JSON; early `exit 0` if tool_name is not Bash,
#   - a SECOND early `exit 0` if the command does not invoke
#     scripts/offers/gmj_firecrawl_search.py — this hook must never interfere with
#     unrelated Bash usage (ls, git status, other scripts, etc.),
#   - log the sources.yaml read + target to .claude/logs/firecrawl-scope.log BEFORE
#     any allow/block decision (the log line is the SC2 demonstrable artifact),
#   - block an off-allow-list --url host, or an off-allow-list domain pinned inside
#     a --query, or an unparseable target, with `exit 2` (+ a {"decision":"block"}
#     object) — fail CLOSED, never fail open.
# Enforces the SAME config/sources.yaml `sites` allow-list as the WebSearch/WebFetch
# hook — never config/credentials.yaml, a semantically different allow-list.
set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
LOG_FILE="${PROJECT_DIR}/.claude/logs/firecrawl-scope.log"
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
timestamp() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(timestamp)] $1" >> "$LOG_FILE" 2>/dev/null || true; }

INPUT_JSON=$(cat)

# Parse a (possibly dotted) field from the stdin JSON — jq with a python3 fallback,
# copied from gmj-sources-scope-guard.sh's read_field (jq may be absent).
read_field() {
  _f="$1"; _v=""
  if command -v jq >/dev/null 2>&1; then
    _v=$(printf '%s' "$INPUT_JSON" | jq -r --arg f "$_f" 'getpath($f | split(".")) // empty' 2>/dev/null || true)
  fi
  if [ -z "$_v" ]; then
    _v=$(printf '%s' "$INPUT_JSON" | FIELD="$_f" python3 -c "import json,os,sys
try:
    d = json.load(sys.stdin)
    for k in os.environ['FIELD'].split('.'):
        d = d[k]
    sys.stdout.write(d if isinstance(d, str) else '')
except Exception:
    pass" 2>/dev/null || true)
  fi
  printf '%s' "$_v"
}

TOOL_NAME=$(read_field tool_name)
COMMAND=$(read_field tool_input.command)

# Detect a genuine python3/python invocation of gmj_firecrawl_search.py — see the
# comment at the call site below for why this replaced a regex-based check.
is_firecrawl_invocation() {
  python3 - "$1" <<'PY' 2>/dev/null
import re, shlex, sys

command = sys.argv[1]
try:
    tokens = shlex.split(command)
except ValueError:
    # Unbalanced quotes etc. — fail closed: treat as a potential invocation so
    # the scope check still runs rather than silently passing through.
    sys.exit(0)


def is_script_token(tok):
    return bool(re.match(r"^[A-Za-z0-9_./-]*gmj_firecrawl_search\.py$", tok))


for idx, tok in enumerate(tokens):
    if tok not in ("python3", "python"):
        continue
    i = idx + 1
    matched = False
    while i < len(tokens):
        t = tokens[i]
        if is_script_token(t):
            matched = True
            break
        if t.startswith("-"):
            i += 1
            continue
        if i > idx + 1 and tokens[i - 1].startswith("-"):
            # a flag's value token (e.g. "utf8" after "-X") — consume, continue
            i += 1
            continue
        break
    if matched:
        sys.exit(0)
sys.exit(1)
PY
}

# Early pass-through: only Bash calls cross this hook's boundary.
if [ "$TOOL_NAME" != "Bash" ]; then
  exit 0
fi

# SECOND early pass-through: only commands that actually INVOKE
# gmj_firecrawl_search.py are gated here — this hook must never interfere with
# unrelated Bash usage (ls, git status, gmj-block-destructive-commands.sh's own
# checks, a git commit message that merely mentions the filename in prose, a
# `git add`/`cat`/editor command referencing its path, etc.). A bare substring
# match on the filename is too broad — it also fires on any command that merely
# REFERENCES the name or path in text (commit messages, `git add <path>`, `cat
# <path>`), none of which are invocations. This script is only ever invoked one
# way per its own CLI contract (plan 48-01): `python3 scripts/offers/gmj_
# firecrawl_search.py ...`. Require that exact interpreter-invocation shape —
# "python"/"python3" immediately followed by a path ending in the script name —
# rather than any bare path or filename mention.
#
# Standard interpreter FLAGS (e.g. `python3 -u ...`, `-B`, `-O`, or value-taking
# flags like `-X utf8`, `-W ignore`) are tolerated between the interpreter and the
# script path. A hand-rolled regex for "python3, then zero or more flag-or-value
# tokens, then the script path" was tightened three separate times against three
# distinct bugs (a filename-mention false positive, a bare-adjacency false negative,
# then a single-token-flag-only false negative that still missed value-taking flags
# like `-X utf8`) — regex cannot express this shape without enumerating every
# Python flag's arity, and each fix reintroduced or missed another edge case.
# Tokenize the command with shlex instead (this also naturally rejects prose
# mentions of the filename inside a quoted string, since shlex keeps a quoted
# phrase as ONE token rather than splitting it into separate words) and walk
# tokens explicitly: after a python3/python token, skip any number of `-flag`
# tokens and at most one non-flag token immediately following each flag (a
# flag's value, e.g. "utf8" after "-X") until the script-path token is reached.
# This hook fails CLOSED on any real invocation shape, never open.
if ! is_firecrawl_invocation "$COMMAND"; then
  exit 0
fi

# Locate the allow-list: prefer the project dir, fall back to the cwd-relative config.
SOURCES_YAML=""
if [ -f "${PROJECT_DIR}/config/sources.yaml" ]; then
  SOURCES_YAML="${PROJECT_DIR}/config/sources.yaml"
elif [ -f "config/sources.yaml" ]; then
  SOURCES_YAML="config/sources.yaml"
fi

# Extract --url value (quoted or bare, stops at whitespace/quote).
URL=$(printf '%s' "$COMMAND" | grep -oE -- '--url[[:space:]]+["'"'"']?[^"'"'"' ]+' 2>/dev/null | sed -E 's/^--url[[:space:]]+["'"'"']?//' || true)

# Extract --query value — may contain spaces inside quotes, so capture through to
# the closing quote character rather than stopping at the first whitespace.
QUERY=$(printf '%s' "$COMMAND" | grep -oE -- '--query[[:space:]]+"[^"]*"|--query[[:space:]]+'"'"'[^'"'"']*'"'"'|--query[[:space:]]+[^[:space:]]+' 2>/dev/null | sed -E 's/^--query[[:space:]]+["'"'"']?//; s/["'"'"']$//' || true)

# SC2: log the sources.yaml read + target BEFORE deciding anything. This line is the
# demonstrable audit record that the read happened ahead of the Firecrawl call.
TARGET="${URL:-$QUERY}"
log "READ ${SOURCES_YAML:-config/sources.yaml} tool=Bash script=gmj_firecrawl_search.py target=${TARGET}"

# Parse allowed hosts from sources.yaml `sites` (yaml if available, else grep https lines).
# Copied verbatim from gmj-sources-scope-guard.sh — do NOT re-derive this logic.
allowed_hosts() {
  [ -z "$SOURCES_YAML" ] && return 0
  [ ! -f "$SOURCES_YAML" ] && return 0
  python3 - "$SOURCES_YAML" <<'PY' 2>/dev/null || true
import re, sys
path = sys.argv[1]
hosts = []
try:
    text = open(path, encoding="utf-8").read()
    sites = []
    try:
        import yaml
        data = yaml.safe_load(text) or {}
        if isinstance(data, dict):
            sites = data.get("sites", []) or []
    except Exception:
        sites = []
    if not sites:
        sites = re.findall(r'https?://[^\s"\']+', text)
    for s in sites:
        h = re.sub(r'^https?://', '', str(s).strip())
        h = h.split('/')[0].split(':')[0]
        h = re.sub(r'^www\.', '', h).lower()
        if h:
            hosts.append(h)
except Exception:
    pass
print("\n".join(sorted(set(hosts))))
PY
}
ALLOWED=$(allowed_hosts)

# Normalize a URL to its bare host (strip scheme, path, leading www., port; lowercase).
# Copied verbatim from gmj-sources-scope-guard.sh.
url_host() {
  printf '%s' "$1" | sed -E 's#^[a-zA-Z][a-zA-Z0-9+.-]*://##; s#/.*$##; s#^www\.##; s#:.*$##' | tr 'A-Z' 'a-z'
}

# A host is allowed on an exact match or as a subdomain of an allowed site host.
# Copied verbatim from gmj-sources-scope-guard.sh.
host_allowed() {
  _h="$1"
  [ -z "$_h" ] && return 1
  for a in $ALLOWED; do
    [ "$_h" = "$a" ] && return 0
    case "$_h" in
      *".$a") return 0 ;;
    esac
  done
  return 1
}

# Scrape-mode call: --url present.
if [ -n "$URL" ]; then
  HOST=$(url_host "$URL")
  if [ -z "$HOST" ]; then
    log "BLOCK tool=Bash script=gmj_firecrawl_search.py reason=unparseable-host url=${URL}"
    echo "BLOCKED: gmj_firecrawl_search.py --url has no parseable host: ${URL}" >&2
    printf '{"decision":"block","reason":%s}\n' '"gmj_firecrawl_search.py --url has no parseable host"'
    exit 2
  fi
  if host_allowed "$HOST"; then
    log "ALLOWED tool=Bash host=${HOST}"
    exit 0
  fi
  log "BLOCK tool=Bash host=${HOST} reason=off-allow-list"
  echo "BLOCKED: ${HOST} is not in config/sources.yaml sites allow-list" >&2
  printf '{"decision":"block","reason":%s}\n' "\"${HOST} not in config/sources.yaml sites allow-list\""
  exit 2
fi

# Search-mode call: --query present, no --url. The hook is the hard domain gate, not
# the query judge. Allow by default, but block a query that explicitly pins an
# off-allow-list domain (site: or a URL) — mirrors the WebSearch branch.
if [ -n "$QUERY" ]; then
  EXPLICIT_HOSTS=$(printf '%s' "$QUERY" \
    | grep -oiE '(site:[a-zA-Z0-9.-]+|https?://[a-zA-Z0-9.-]+)' 2>/dev/null \
    | sed -E 's#^[sS][iI][tT][eE]:##; s#^[a-zA-Z][a-zA-Z0-9+.-]*://##; s#/.*$##; s#^www\.##' \
    | tr 'A-Z' 'a-z' || true)
  for h in $EXPLICIT_HOSTS; do
    if ! host_allowed "$h"; then
      log "BLOCK tool=Bash host=${h} reason=off-allow-list-in-query"
      echo "BLOCKED: query pins ${h}, not in config/sources.yaml sites allow-list" >&2
      printf '{"decision":"block","reason":%s}\n' "\"${h} not in config/sources.yaml sites allow-list\""
      exit 2
    fi
  done
  log "ALLOWED tool=Bash query=${QUERY}"
  exit 0
fi

# Neither --url nor --query extractable from a command matching gmj_firecrawl_search.py
# — malformed/unparseable target. Fail CLOSED, never fail open (matches
# gmj_validate_preferences.py's fail-closed convention).
log "BLOCK tool=Bash script=gmj_firecrawl_search.py reason=unparseable-target command=${COMMAND}"
echo "BLOCKED: gmj_firecrawl_search.py command has no parseable --url or --query target" >&2
printf '{"decision":"block","reason":%s}\n' '"gmj_firecrawl_search.py command has no parseable --url or --query target"'
exit 2
