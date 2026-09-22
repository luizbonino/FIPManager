#!/usr/bin/env bash
# Everything that must pass before a push or a PR.
#
#   scripts/check.sh          backend + frontend  (~1 min)
#   scripts/check.sh --quick  lint and type-check only, no test suites (~15 s)
#   scripts/check.sh --full   adds the Docker image build (~3 min)
#
# Runs every stage even after one fails, so a single run tells you everything
# that is wrong rather than only the first thing. Exit status is non-zero if
# any stage failed.
#
# This is a superset of .github/workflows/ci.yml: CI does not run the frontend
# test suite, so `npm run test` here is the only thing that runs those specs
# before they reach main.
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"

MODE="normal"
case "${1:-}" in
  --quick) MODE="quick" ;;
  --full)  MODE="full" ;;
  "")      ;;
  *) echo "usage: $0 [--quick|--full]" >&2; exit 2 ;;
esac

if [ -t 1 ]; then
  RED=$'\033[31m'; GREEN=$'\033[32m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; OFF=$'\033[0m'
else
  RED=""; GREEN=""; DIM=""; BOLD=""; OFF=""
fi

FAILED=()
PASSED=0

# stage <name> <dir> <command...>
stage() {
  local name="$1" dir="$2"; shift 2
  printf '%s>> %s%s\n' "$BOLD" "$name" "$OFF"
  local start=$SECONDS out status
  # Keep the output; show it only on failure so a green run stays readable.
  out=$(cd "$ROOT/$dir" && "$@" 2>&1); status=$?
  local secs=$(( SECONDS - start ))
  if [ $status -eq 0 ]; then
    printf '   %sok%s %s(%ss)%s\n' "$GREEN" "$OFF" "$DIM" "$secs" "$OFF"
    PASSED=$(( PASSED + 1 ))
  else
    printf '   %sFAILED%s %s(%ss)%s\n' "$RED" "$OFF" "$DIM" "$secs" "$OFF"
    printf '%s\n' "$out" | tail -40 | sed 's/^/   | /'
    FAILED+=("$name")
  fi
}

echo "FIP Manager checks  ${DIM}(mode: $MODE)${OFF}"
echo

stage "backend   lint"        backend  uv run ruff check .
stage "backend   format"      backend  uv run ruff format --check
if [ "$MODE" != "quick" ]; then
  stage "backend   tests"     backend  uv run pytest -q
fi

stage "frontend  type-check"  frontend npx vue-tsc --noEmit
if [ "$MODE" != "quick" ]; then
  stage "frontend  tests"     frontend npm run test
fi
stage "frontend  build"       frontend npm run build

if [ "$MODE" = "full" ]; then
  stage "docker    image"     .        docker build -q .
fi

echo
if [ ${#FAILED[@]} -eq 0 ]; then
  printf '%sAll %d checks passed.%s\n' "$GREEN" "$PASSED" "$OFF"
  exit 0
fi
printf '%s%d failed:%s %s\n' "$RED" "${#FAILED[@]}" "$OFF" "${FAILED[*]}"
exit 1
