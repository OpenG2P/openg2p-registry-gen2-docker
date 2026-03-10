# =============================================================================
# scripts/README.md — Local build scripts for openg2p-registry-gen2-docker
# =============================================================================

## Overview

The `scripts/` folder provides a fully local, command-line equivalent of the
**docker-build.yml** GitHub Actions workflow.  Running `build.sh` does exactly
what the workflow does:

1. Reads a **service spec file** (e.g. `staff-portal-api/farmer-develop.txt`)
2. Parses the Docker image tag, git dependencies, and Dockerfile path
3. Generates `adapters.requirements.txt` in the repo root (consumed by the Dockerfiles)
4. Runs `docker build` with all OCI labels and `--build-arg` values
5. Optionally pushes to Docker Hub

---

## Files

| File | Purpose |
|------|---------|
| `build.sh` | Main entry point — orchestrates everything |
| `parse_service.py` | Python helper that parses service spec files (mirrors the GH Actions Python step) |
| `.env.example` | Template for Docker Hub credentials — copy to `.env` and fill in |
| `README.md` | This file |

---

## Quick Start

### 1. Set up credentials

```bash
cp scripts/.env.example scripts/.env
# Edit scripts/.env and fill in DOCKER_HUB_USERNAME and DOCKER_HUB_TOKEN
```

> `.env` is gitignored — never commit it.

### 2. Make the script executable (first time only)

```bash
chmod +x scripts/build.sh
```

### 3. Build all default services (no push)

```bash
cd /path/to/openg2p-registry-gen2-docker
./scripts/build.sh
```

### 4. Build a single service

```bash
./scripts/build.sh staff-portal-api/farmer-develop.txt
./scripts/build.sh celery/farmer-develop.txt
./scripts/build.sh partner-api/farmer-develop.txt
./scripts/build.sh staff-portal-ui/develop.txt
```

### 5. Build and push to Docker Hub

```bash
./scripts/build.sh --push staff-portal-api/farmer-develop.txt
# or set env var:
PUSH=1 ./scripts/build.sh
```

### 6. Multi-arch build (amd64 + arm64) and push

```bash
./scripts/build.sh --platform linux/amd64,linux/arm64 --push staff-portal-api/farmer-develop.txt
# or:
BUILD_PLATFORM=linux/amd64,linux/arm64 PUSH=1 ./scripts/build.sh
```

> Multi-arch builds require Docker Buildx (installed by default in Docker Desktop).

### 7. Build without cache

```bash
./scripts/build.sh --no-cache staff-portal-api/farmer-develop.txt
# or:
NO_CACHE=1 ./scripts/build.sh
```

### 8. Override Dockerfile path

```bash
./scripts/build.sh --dockerfile celery/Dockerfile celery/farmer-develop.txt
```

---

## Environment Variables

All options can be set via environment variables instead of CLI flags:

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCKER_HUB_USERNAME` | — | Docker Hub username (required for push) |
| `DOCKER_HUB_TOKEN` | — | Docker Hub access token (required for push) |
| `PUSH` | `0` | Set to `1` to push after build |
| `NO_CACHE` | `0` | Set to `1` to disable Docker layer cache |
| `BUILD_PLATFORM` | `linux/amd64` | Platform(s) to build for |

---

## Service Spec File Format

The service files (e.g. `staff-portal-api/farmer-develop.txt`) follow this format:

```
#!docker-org/image-name:tag          ← required: Docker image to produce
# optional comments

git://BRANCH_OR_TAG//GITHUB_URL#subdirectory=pkg  ← git pip dependency
git://v1.2.3//https://github.com/org/repo#subdirectory=subpkg
regular-pypi-package==1.0.0          ← plain pip dependency
```

The script converts each `git://` line into a pip-installable URL of the form:
`git+https://github.com/org/repo@BRANCH#subdirectory=pkg`

These are written to `adapters.requirements.txt`, which the Dockerfiles `COPY`
and `pip install` during the build.

The **Dockerfile** is resolved in this order:
1. `--dockerfile` CLI argument
2. `Dockerfile` in the same directory as the spec file
3. A second `#!` line in the spec file (legacy format)

---

## Default Service Matrix

When called with no arguments, `build.sh` builds all four services:

| Service | Spec File |
|---------|-----------|
| staff-portal-api | `staff-portal-api/farmer-develop.txt` |
| celery | `celery/farmer-develop.txt` |
| partner-api | `partner-api/farmer-develop.txt` |
| staff-portal-ui | `staff-portal-ui/develop.txt` |

---

## Requirements

- **Docker** ≥ 20 with Buildx (for multi-arch; standard builds work without it)
- **Python** ≥ 3.10 (for `parse_service.py`)
- **git** in PATH
- A valid Docker Hub account with push access to the target image names
