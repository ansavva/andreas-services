#!/usr/bin/env bash
#
# Trigger a production deploy and watch it to completion.
#
# Every prod workflow already runs on push to main with path filtering, so this
# is for the cases push cannot express: re-running a deploy after fixing state
# out of band, deploying a service whose files did not change (the path filter
# skips it), and the cross-service ordering that shows up after a rename —
# mailer republishes SSM, then humbugg has to apply to pick the new values up.
#
# Usage:
#   ./scripts/deploy.sh website                 # full deploy, watch until it ends
#   ./scripts/deploy.sh humbugg --app-only      # skip Terraform, ship code only
#   ./scripts/deploy.sh mailer --infra-only     # Terraform only
#   ./scripts/deploy.sh shared                  # shared infra (takes no inputs)
#   ./scripts/deploy.sh website --no-watch      # dispatch and return immediately
#   ./scripts/deploy.sh website --dry-run       # print the gh command, run nothing
#   ./scripts/deploy.sh --status                # last run per service, no trigger
#
# Exits non-zero when the watched run fails, so it chains:
#   ./scripts/deploy.sh mailer && ./scripts/deploy.sh humbugg
#
set -euo pipefail

SERVICES="humbugg mailer scout storybook website shared"

workflow_for() {
  case "$1" in
    humbugg)   echo humbugg-prod.yaml ;;
    mailer)    echo mailer-prod.yaml ;;
    scout)     echo scout-prod.yaml ;;
    storybook) echo storybook-prod.yaml ;;
    website)   echo website-prod.yaml ;;
    shared)    echo shared-prod-infra-deploy.yaml ;;
    *)         return 1 ;;
  esac
}

# The header block above, minus its leading "# ". Bounded by the first
# non-comment line rather than a line number, so editing the header cannot
# silently start printing code.
usage() { sed -n '3,$p' "$0" | sed -n '/^#/p;/^#/!q' | sed 's/^# \{0,1\}//'; }

die() { echo "error: $*" >&2; exit 1; }

# `gh run list` needs a repo and a login; failing here beats failing halfway
# through a dispatch with no way to tell whether it landed.
preflight() {
  command -v gh >/dev/null 2>&1 || die "the GitHub CLI (gh) is not installed"
  gh auth status >/dev/null 2>&1 || die "gh is not authenticated — run 'gh auth login'"
}

latest_run_id() { # workflow file -> id of its most recent run, or 0
  gh run list --workflow="$1" --limit 1 --json databaseId \
    --jq '.[0].databaseId // 0' 2>/dev/null || echo 0
}

status_report() {
  printf '%-11s %-9s %-9s %s\n' SERVICE STATUS RESULT WHEN
  for svc in ${SERVICES}; do
    local wf row
    wf="$(workflow_for "${svc}")"
    row="$(gh run list --workflow="${wf}" --limit 1 \
      --json status,conclusion,createdAt \
      --jq '.[0] | "\(.status)\t\(.conclusion // "-")\t\(.createdAt)"' 2>/dev/null || true)"
    [[ -z "${row}" ]] && row=$'(none)\t-\t-'
    printf '%-11s %-9s %-9s %s\n' "${svc}" $(echo "${row}" | tr '\t' ' ')
  done
}

SERVICE=""
REF="main"
RUN_INFRA="true"
RUN_APP="true"
WATCH=1
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)   usage; exit 0 ;;
    --status)    preflight; status_report; exit 0 ;;
    --infra-only) RUN_APP="false" ;;
    --app-only)  RUN_INFRA="false" ;;
    --no-watch)  WATCH=0 ;;
    --dry-run)   DRY_RUN=1 ;;
    --ref)       REF="${2:-}"; [[ -n "${REF}" ]] || die "--ref needs a value"; shift ;;
    -*)          die "unknown flag: $1" ;;
    *)           [[ -z "${SERVICE}" ]] || die "one service at a time (got '${SERVICE}' and '$1')"
                 SERVICE="$1" ;;
  esac
  shift
done

[[ -n "${SERVICE}" ]] || { usage; exit 1; }
WORKFLOW="$(workflow_for "${SERVICE}")" || die "unknown service '${SERVICE}' (one of: ${SERVICES})"

if [[ "${RUN_INFRA}" == "false" && "${RUN_APP}" == "false" ]]; then
  die "--infra-only and --app-only are mutually exclusive"
fi

# The shared infra workflow declares workflow_dispatch with no inputs at all, so
# passing run_infra/run_app to it is a hard error from the API rather than a
# no-op. Nothing to split there anyway: the whole workflow is one apply.
INPUTS=()
if [[ "${SERVICE}" == "shared" ]]; then
  if [[ "${RUN_INFRA}" == "false" || "${RUN_APP}" == "false" ]]; then
    die "shared infra takes no inputs — drop --infra-only/--app-only"
  fi
else
  INPUTS=(-f "run_infra=${RUN_INFRA}" -f "run_app=${RUN_APP}")
fi

preflight

echo "service:  ${SERVICE}"
echo "workflow: ${WORKFLOW}"
echo "ref:      ${REF}"
[[ ${#INPUTS[@]} -gt 0 ]] && echo "inputs:   run_infra=${RUN_INFRA} run_app=${RUN_APP}"

if (( DRY_RUN )); then
  echo
  echo "would run: gh workflow run ${WORKFLOW} --ref ${REF} ${INPUTS[*]}"
  exit 0
fi

# Prod workflows are gated to main on push, but workflow_dispatch will happily
# apply any ref against production. Deploying a branch is occasionally what you
# want and never what you want by accident.
if [[ "${REF}" != "main" ]]; then
  read -r -p "Deploy ref '${REF}' to PRODUCTION? Type the ref to confirm: " reply
  [[ "${reply}" == "${REF}" ]] || { echo "Aborted."; exit 1; }
fi

BEFORE="$(latest_run_id "${WORKFLOW}")"
gh workflow run "${WORKFLOW}" --ref "${REF}" ${INPUTS[@]+"${INPUTS[@]}"}

# `gh workflow run` returns nothing identifying the run it just queued, so watch
# for a new id rather than assuming the newest one is ours — a push-triggered run
# landing at the same moment would otherwise be the one reported on.
RUN_ID=""
for _ in $(seq 1 30); do
  sleep 2
  candidate="$(latest_run_id "${WORKFLOW}")"
  if [[ "${candidate}" != "${BEFORE}" && "${candidate}" != "0" ]]; then
    RUN_ID="${candidate}"
    break
  fi
done

if [[ -z "${RUN_ID}" ]]; then
  echo "Dispatched, but no new run appeared within 60s. Check:" >&2
  echo "  gh run list --workflow=${WORKFLOW}" >&2
  exit 1
fi

echo "run:      $(gh run view "${RUN_ID}" --json url --jq .url)"

if (( ! WATCH )); then
  exit 0
fi

echo
gh run watch "${RUN_ID}" --exit-status
