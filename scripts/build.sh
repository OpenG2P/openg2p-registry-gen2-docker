#!/usr/bin/env bash
# =============================================================================
# build.sh — Local CLI equivalent of the docker-build.yml GitHub Actions workflow
#
# Usage:
#   ./build.sh [OPTIONS] [SERVICE_FILE]
#
# Examples:
#   ./build.sh                                          # Build all default services
#   ./build.sh staff-portal-api/farmer-develop.txt      # Build one service
#   ./build.sh --push staff-portal-api/farmer-develop.txt
#   ./build.sh --dockerfile staff-portal-api/Dockerfile staff-portal-api/farmer-develop.txt
#   ./build.sh --platform linux/amd64 --push all
#
# Required env vars (set in .env or export before running):
#   DOCKER_HUB_USERNAME   — Docker Hub username
#   DOCKER_HUB_TOKEN      — Docker Hub access token / password
#
# Optional env vars:
#   BUILD_PLATFORM        — Docker platform(s), default: linux/amd64
#                           Use linux/amd64,linux/arm64 for multi-arch (slower, needs buildx)
#   NO_CACHE              — Set to "1" to disable Docker build cache
#   PUSH                  — Set to "1" to push after build (overrides --push flag)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
PUSH="${PUSH:-0}"
NO_CACHE="${NO_CACHE:-0}"
BUILD_PLATFORM="${BUILD_PLATFORM:-linux/amd64}"
OVERRIDE_DOCKERFILE=""

# Default service matrix (mirrors the workflow's fallback list)
DEFAULT_SERVICES=(
  "staff-portal-api/farmer-develop.txt"
  "celery/farmer-develop.txt"
  "partner-api/farmer-develop.txt"
  "staff-portal-ui/develop.txt"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo "[build.sh] $*"; }
err()  { echo "[build.sh] ERROR: $*" >&2; }
die()  { err "$*"; exit 1; }

usage() {
  grep '^#' "$0" | grep -v '#!/' | sed 's/^# \{0,2\}//'
  exit 0
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
POSITIONAL=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)        usage ;;
    --push)           PUSH=1; shift ;;
    --no-cache)       NO_CACHE=1; shift ;;
    --platform)       BUILD_PLATFORM="$2"; shift 2 ;;
    --dockerfile)     OVERRIDE_DOCKERFILE="$2"; shift 2 ;;
    *)                POSITIONAL+=("$1"); shift ;;
  esac
done

# Determine which service files to build
SERVICE_FILES=()
if [[ ${#POSITIONAL[@]} -eq 0 || "${POSITIONAL[0]:-}" == "all" ]]; then
  SERVICE_FILES=("${DEFAULT_SERVICES[@]}")
else
  SERVICE_FILES=("${POSITIONAL[@]}")
fi

# ---------------------------------------------------------------------------
# Credential check
# ---------------------------------------------------------------------------
if [[ "${PUSH}" == "1" ]]; then
  # Load .env if present
  ENV_FILE="${SCRIPT_DIR}/.env"
  if [[ -f "${ENV_FILE}" ]]; then
    log "Loading credentials from ${ENV_FILE}"
    # shellcheck disable=SC1090
    set -a; source "${ENV_FILE}"; set +a
  fi
  [[ -n "${DOCKER_HUB_USERNAME:-}" ]] || die "DOCKER_HUB_USERNAME is not set. Set it in scripts/.env or export it."
  [[ -n "${DOCKER_HUB_TOKEN:-}"    ]] || die "DOCKER_HUB_TOKEN is not set. Set it in scripts/.env or export it."

  log "Logging in to Docker Hub as ${DOCKER_HUB_USERNAME}..."
  echo "${DOCKER_HUB_TOKEN}" | docker login --username "${DOCKER_HUB_USERNAME}" --password-stdin
fi

# ---------------------------------------------------------------------------
# Multi-arch buildx setup (only if needed)
# ---------------------------------------------------------------------------
if [[ "${BUILD_PLATFORM}" == *","* ]]; then
  log "Multi-arch build requested (${BUILD_PLATFORM}). Setting up buildx builder..."
  if ! docker buildx inspect openg2p-builder &>/dev/null; then
    docker buildx create --name openg2p-builder --use
  else
    docker buildx use openg2p-builder
  fi
  docker buildx inspect --bootstrap
  BUILDX=1
else
  BUILDX=0
fi

# ---------------------------------------------------------------------------
# Process each service file
# ---------------------------------------------------------------------------
FAILURES=()

for SERVICE_FILE in "${SERVICE_FILES[@]}"; do
  # Resolve relative to repo root
  if [[ ! "${SERVICE_FILE}" = /* ]]; then
    SERVICE_FILE="${REPO_ROOT}/${SERVICE_FILE}"
  fi

  log "============================================================"
  log "Processing service file: ${SERVICE_FILE}"
  log "============================================================"

  # Run the Python parse+build helper (mirrors the workflow's Python step)
  python3 "${SCRIPT_DIR}/parse_service.py" \
    --service-file "${SERVICE_FILE}" \
    --repo-root    "${REPO_ROOT}" \
    ${OVERRIDE_DOCKERFILE:+--dockerfile "${OVERRIDE_DOCKERFILE}"} \
    --output-env   "${SCRIPT_DIR}/_service_env.sh"

  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/_service_env.sh"

  log "Image      : ${SVC_IMAGE}"
  log "Dockerfile : ${SVC_DOCKERFILE}"
  log "Context    : ${SVC_CONTEXT}"
  log "REPO_URL   : ${SVC_REPO_URL}"
  log "GIT_BRANCH : ${SVC_GIT_BRANCH}"

  log "Generated adapters.requirements.txt:"
  cat "${REPO_ROOT}/adapters.requirements.txt"
  echo ""

  # Build args
  BUILD_ARGS=(
    -f "${SVC_DOCKERFILE}"
    -t "${SVC_IMAGE}"
    --build-arg "REPO_URL=${SVC_REPO_URL}"
    --build-arg "GIT_BRANCH=${SVC_GIT_BRANCH}"
    --label "org.opencontainers.image.created=${SVC_CREATED}"
    --label "org.opencontainers.image.revision=${SVC_COMMIT}"
    --label "org.opencontainers.image.vendor=${SVC_VENDOR}"
    --label "org.opencontainers.image.title=${SVC_TITLE}"
    --label "org.opencontainers.image.version=${SVC_VERSION}"
    --label "org.opencontainers.image.description=OpenG2P Registry Gen2 service image"
  )

  [[ "${NO_CACHE}" == "1" ]] && BUILD_ARGS+=(--no-cache)

  if [[ "${BUILDX}" == "1" ]]; then
    # buildx build with multi-platform
    PUSH_FLAG="--load"
    [[ "${PUSH}" == "1" ]] && PUSH_FLAG="--push"
    log "Running: docker buildx build --platform ${BUILD_PLATFORM} ${PUSH_FLAG} ..."
    if docker buildx build \
        --platform "${BUILD_PLATFORM}" \
        "${BUILD_ARGS[@]}" \
        ${PUSH_FLAG} \
        "${SVC_CONTEXT}"; then
      log "✅ Build succeeded: ${SVC_IMAGE}"
    else
      err "❌ Build failed: ${SVC_IMAGE}"
      FAILURES+=("${SVC_IMAGE}")
    fi
  else
    # Standard docker build
    log "Running: docker build ..."
    if docker build "${BUILD_ARGS[@]}" "${SVC_CONTEXT}"; then
      log "✅ Build succeeded: ${SVC_IMAGE}"
      if [[ "${PUSH}" == "1" ]]; then
        log "Pushing ${SVC_IMAGE}..."
        docker push "${SVC_IMAGE}"
      fi
    else
      err "❌ Build failed: ${SVC_IMAGE}"
      FAILURES+=("${SVC_IMAGE}")
    fi
  fi

  # Cleanup temp env file
  rm -f "${SCRIPT_DIR}/_service_env.sh"
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
log "============================================================"
log "Build Summary"
log "============================================================"
TOTAL=${#SERVICE_FILES[@]}
FAILED=${#FAILURES[@]}
PASSED=$(( TOTAL - FAILED ))
log "Total: ${TOTAL}  Passed: ${PASSED}  Failed: ${FAILED}"

if [[ ${FAILED} -gt 0 ]]; then
  err "The following builds failed:"
  for f in "${FAILURES[@]}"; do
    err "  - ${f}"
  done
  exit 1
fi

log "All builds completed successfully."
