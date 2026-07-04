#!/usr/bin/env sh
# PreToolUse — enforce config/sources.yaml scope on every WebSearch/WebFetch (INTAKE-05).
#
# SC2 requires the sources.yaml read to be DEMONSTRABLY happening before any web search.
# An agent self-report in `notes` is not demonstrable; a logged machine check is
# (RESEARCH Pattern 5, Pitfall 5). This mirrors the Phase 2 decision to enforce via
# executed hooks, not hub-side trust.
#
# Contract (RESEARCH PreToolUse hook contract):
#   - read stdin JSON; early `exit 0` if tool_name is neither WebSearch nor WebFetch,
#   - log the sources.yaml read + target to .claude/logs/sources-scope.log BEFORE any
#     allow/block decision (the log line is the SC2 demonstrable artifact),
#   - block an off-allow-list WebFetch host with `exit 2` (+ a {"decision":"block"} object).
# The hook is the hard DOMAIN gate; cities/languages/limits stay the agent-side
# gmj-sources-config-enforcement skill's job (do NOT weaken that skill).
set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
LOG_FILE="${PROJECT_DIR}/.claude/logs/sources-scope.log"
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
timestamp() { date '+%Y-%m-%d %H:%M:%S'; }
log() { echo "[$(timestamp)] $1" >> "$LOG_FILE" 2>/dev/null || true; }

# Credential fetches (INGEST-02) get a DISTINCT audit log, separate from the
# job-board sources-scope.log — the demonstrable record that a credential URL was
# authorized by config/credentials.yaml, not by the offer-search scope.
CRED_LOG_FILE="${PROJECT_DIR}/.claude/logs/credential-intake.log"
log_cred() {
  mkdir -p "$(dirname "$CRED_LOG_FILE")" 2>/dev/null || true
  echo "[$(timestamp)] $1" >> "$CRED_LOG_FILE" 2>/dev/null || true
}

INPUT_JSON=$(cat)

# Parse a (possibly dotted) field from the stdin JSON — jq with a python3 fallback,
# copied from validate-envelope.sh read_field (jq may be absent).
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
URL=$(read_field tool_input.url)
QUERY=$(read_field tool_input.query)

# Early pass-through: only WebSearch/WebFetch cross the gmj-offer-scout -> web boundary.
if [ "$TOOL_NAME" != "WebSearch" ] && [ "$TOOL_NAME" != "WebFetch" ]; then
  exit 0
fi

# Locate the allow-list: prefer the project dir, fall back to the cwd-relative config.
SOURCES_YAML=""
if [ -f "${PROJECT_DIR}/config/sources.yaml" ]; then
  SOURCES_YAML="${PROJECT_DIR}/config/sources.yaml"
elif [ -f "config/sources.yaml" ]; then
  SOURCES_YAML="config/sources.yaml"
fi

# Locate the SEPARATE credential allow-list the same way (INGEST-02, Option A).
CREDENTIALS_YAML=""
if [ -f "${PROJECT_DIR}/config/credentials.yaml" ]; then
  CREDENTIALS_YAML="${PROJECT_DIR}/config/credentials.yaml"
elif [ -f "config/credentials.yaml" ]; then
  CREDENTIALS_YAML="config/credentials.yaml"
fi

# SC2: log the sources.yaml read + target BEFORE deciding anything. This line is the
# demonstrable audit record that the read happened ahead of the web access.
TARGET="${URL:-$QUERY}"
log "READ ${SOURCES_YAML:-config/sources.yaml} tool=${TOOL_NAME} target=${TARGET}"

# Parse allowed hosts from sources.yaml `sites` (yaml if available, else grep https lines).
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

# Parse the SEPARATE credential allow-list from credentials.yaml `credential_sites`,
# with identical scheme/www/lowercase host normalization to allowed_hosts().
credential_hosts() {
  [ -z "$CREDENTIALS_YAML" ] && return 0
  [ ! -f "$CREDENTIALS_YAML" ] && return 0
  python3 - "$CREDENTIALS_YAML" <<'PY' 2>/dev/null || true
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
            sites = data.get("credential_sites", []) or []
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
CREDENTIAL_ALLOWED=$(credential_hosts)

# Normalize a URL to its bare host (strip scheme, path, leading www., port; lowercase).
url_host() {
  printf '%s' "$1" | sed -E 's#^[a-zA-Z][a-zA-Z0-9+.-]*://##; s#/.*$##; s#^www\.##; s#:.*$##' | tr 'A-Z' 'a-z'
}

# A host is allowed on an exact match or as a subdomain of an allowed site host.
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

# A host is credential-allowed on an exact match or as a subdomain of a
# credential_sites host (mirrors host_allowed against CREDENTIAL_ALLOWED).
credential_host_allowed() {
  _h="$1"
  [ -z "$_h" ] && return 1
  for a in $CREDENTIAL_ALLOWED; do
    [ "$_h" = "$a" ] && return 0
    case "$_h" in
      *".$a") return 0 ;;
    esac
  done
  return 1
}

if [ "$TOOL_NAME" = "WebFetch" ]; then
  HOST=$(url_host "$URL")
  if [ -z "$HOST" ]; then
    log "BLOCK tool=WebFetch reason=unparseable-host url=${URL}"
    echo "BLOCKED: WebFetch URL has no parseable host: ${URL}" >&2
    printf '{"decision":"block","reason":%s}\n' '"WebFetch URL has no parseable host"'
    exit 2
  fi
  if host_allowed "$HOST"; then
    log "ALLOWED tool=WebFetch host=${HOST}"
    exit 0
  elif credential_host_allowed "$HOST"; then
    # Authorized by the SEPARATE credential list — allow + record in the distinct
    # credential-intake audit log (INGEST-02), not the job-board sources-scope.log.
    log_cred "ALLOWED tool=WebFetch host=${HOST} reason=credential-allow-list"
    exit 0
  fi
  log "BLOCK tool=WebFetch host=${HOST} reason=off-allow-list"
  echo "BLOCKED: ${HOST} is not in config/sources.yaml sites allow-list" >&2
  printf '{"decision":"block","reason":%s}\n' "\"${HOST} not in config/sources.yaml sites allow-list\""
  exit 2
fi

# WebSearch: the hook is the hard domain gate, not the query judge. Allow by default,
# but block a query that explicitly pins an off-allow-list domain (site: or a URL).
EXPLICIT_HOSTS=$(printf '%s' "$QUERY" \
  | grep -oiE '(site:[a-zA-Z0-9.-]+|https?://[a-zA-Z0-9.-]+)' 2>/dev/null \
  | sed -E 's#^[sS][iI][tT][eE]:##; s#^[a-zA-Z][a-zA-Z0-9+.-]*://##; s#/.*$##; s#^www\.##' \
  | tr 'A-Z' 'a-z' || true)
for h in $EXPLICIT_HOSTS; do
  if ! host_allowed "$h"; then
    log "BLOCK tool=WebSearch host=${h} reason=off-allow-list-in-query"
    echo "BLOCKED: query pins ${h}, not in config/sources.yaml sites allow-list" >&2
    printf '{"decision":"block","reason":%s}\n' "\"${h} not in config/sources.yaml sites allow-list\""
    exit 2
  fi
done
log "ALLOWED tool=WebSearch query=${QUERY}"
exit 0
