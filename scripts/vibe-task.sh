#!/usr/bin/env bash
# Run a well-specified task through Mistral Vibe in programmatic mode and print
# only the final assistant message. Tokens spent here are on the Mistral plan,
# not on Claude.
#
# Usage: scripts/vibe-task.sh [--turns N] [--price USD] [--readonly] "<prompt>"
#   --turns N    max assistant turns (default 15)
#   --price USD  cost cap (default 0.50; ignored on free plan)
#   --readonly   allow only read/search tools, no edits
# The prompt should contain: goal, files to touch, acceptance criteria, and
# "Finish with a summary of files changed as path:line".
set -euo pipefail
VIBE="${VIBE_BIN:-$(command -v vibe || echo "$HOME/.local/bin/vibe")}"
TURNS=15; PRICE=0.50; TOOLS=()
while [[ $# -gt 1 ]]; do
  case "$1" in
    --turns) TURNS="$2"; shift 2;;
    --price) PRICE="$2"; shift 2;;
    --readonly) TOOLS=(--enabled-tools read_file --enabled-tools grep); shift;;
    *) echo "unknown option $1" >&2; exit 2;;
  esac
done
PROMPT="${1:?prompt required}"
[[ -x "$VIBE" ]] || { echo "vibe not found at $VIBE (uv tool install mistral-vibe)" >&2; exit 127; }

OUT="$(mktemp)"
trap 'rm -f "$OUT"' EXIT
set +e
"$VIBE" -p "$PROMPT" --auto-approve --max-turns "$TURNS" --max-price "$PRICE" --output json "${TOOLS[@]:-}" >"$OUT" 2>"$OUT.err"
RC=$?
set -e
python3 - "$OUT" <<'PY'
import json, sys
try:
    entries = json.load(open(sys.argv[1]))
except Exception as e:
    print(f"[vibe-task] could not parse output: {e}", file=sys.stderr); sys.exit(1)
msgs = [e for e in entries if e.get("type") == "message" and e.get("role") == "assistant"]
tools = [e for e in entries if e.get("type") not in ("message", "reasoning")]
if not msgs:
    print("[vibe-task] no assistant message returned", file=sys.stderr); sys.exit(1)
for c in msgs[-1].get("content", []):
    if c.get("type") == "text":
        print(c["text"])
print(f"\n[vibe-task] turns={len(msgs)} tool_events={len(tools)}", file=sys.stderr)
PY
if [[ $RC -ne 0 ]]; then echo "[vibe-task] vibe exited $RC:"; tail -20 "$OUT.err"; fi
rm -f "$OUT.err"
exit $RC
