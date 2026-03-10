#!/usr/bin/env python3
"""
parse_service.py — Parses an OpenG2P service spec file and emits a shell-sourceable
env file plus the adapters.requirements.txt consumed by the Dockerfiles.

This is a direct Python equivalent of the "Read service file and prepare adapters
requirements" step in docker-build.yml.

Usage (called by build.sh, but can also be run directly):
    python3 parse_service.py \
        --service-file staff-portal-api/farmer-develop.txt \
        --repo-root    /path/to/repo \
        [--dockerfile  staff-portal-api/Dockerfile] \
        [--output-env  /tmp/service_env.sh]
"""

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime


def parse_service_file(service_file: str, override_dockerfile: str | None, repo_root: str):
    """Parse the service spec file and return a dict of all derived values."""
    service_file = os.path.abspath(service_file)
    if not os.path.exists(service_file):
        print(f"Error: Service file not found: {service_file}", file=sys.stderr)
        sys.exit(1)

    with open(service_file) as f:
        lines = [line.strip() for line in f if line.strip()]

    if not lines or not lines[0].startswith("#!"):
        print("Error: Invalid service file format. First line must be '#!IMAGE_ID'", file=sys.stderr)
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Line 1 — Docker image tag
    # -----------------------------------------------------------------------
    image_id = lines[0].lstrip("#!").strip()

    # -----------------------------------------------------------------------
    # Dockerfile resolution (mirrors workflow logic)
    # -----------------------------------------------------------------------
    dockerfile = override_dockerfile or ""

    if not dockerfile:
        # 1. Same directory as the service file
        service_dir = os.path.dirname(service_file)
        candidate = os.path.join(service_dir, "Dockerfile")
        if os.path.exists(candidate):
            dockerfile = candidate

    if not dockerfile and len(lines) > 1 and lines[1].startswith("#!"):
        # 2. Legacy: second line is #!Dockerfile path
        dockerfile = lines[1].lstrip("#!").strip()

    if not dockerfile:
        print(
            f"Error: Could not determine Dockerfile for {service_file}. "
            "Pass --dockerfile explicitly.",
            file=sys.stderr,
        )
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Dependency / git line parsing
    # -----------------------------------------------------------------------
    deps = []
    repo_url = ""
    git_branch = ""

    for line in lines:
        if line.startswith("#"):
            continue
        val = line.strip()
        if not val:
            continue

        # git://TAG//URL[#subdirectory=...]
        m = re.match(r"git://([^/]+)//(.+)", val)
        if m:
            tag = m.group(1)
            url_full = m.group(2)
            # Capture first git dep as primary repo/branch (used for Dockerfile ARGs)
            if not repo_url:
                repo_url = url_full.split("#")[0] if "#" in url_full else url_full
                git_branch = tag
            if "#" in url_full:
                base, frag = url_full.split("#", 1)
                deps.append(f"git+{base}@{tag}#{frag}")
            else:
                deps.append(f"git+{url_full}@{tag}")
        else:
            deps.append(val)

    # -----------------------------------------------------------------------
    # Write adapters.requirements.txt into repo root (Dockerfiles COPY it)
    # -----------------------------------------------------------------------
    req_path = os.path.join(repo_root, "adapters.requirements.txt")
    with open(req_path, "w") as f:
        f.write("\n".join(deps))
        if deps:
            f.write("\n")

    print("---- adapters.requirements.txt ----")
    print("\n".join(deps) or "(empty)")
    print("-----------------------------------")

    # -----------------------------------------------------------------------
    # Git metadata for OCI labels
    # -----------------------------------------------------------------------
    try:
        commit_hash = (
            subprocess.check_output(
                ["git", "--no-pager", "log", "-1", "--pretty=format:%H"],
                cwd=repo_root,
            )
            .decode()
            .strip()
        )
    except Exception:
        commit_hash = "unknown"

    created = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    vendor = image_id.split("/")[0] if "/" in image_id else "unknown"
    try:
        title = image_id.split("/")[1].split(":")[0]
    except IndexError:
        title = image_id

    version = image_id.split(":")[-1] if ":" in image_id else "latest"

    # Make dockerfile path absolute consistently
    if not os.path.isabs(dockerfile):
        dockerfile = os.path.join(repo_root, dockerfile)
    dockerfile = os.path.abspath(dockerfile)

    return {
        "SVC_IMAGE":      image_id,
        "SVC_DOCKERFILE": dockerfile,
        "SVC_CONTEXT":    repo_root,
        "SVC_REPO_URL":   repo_url,
        "SVC_GIT_BRANCH": git_branch,
        "SVC_CREATED":    created,
        "SVC_COMMIT":     commit_hash,
        "SVC_VENDOR":     vendor,
        "SVC_TITLE":      title,
        "SVC_VERSION":    version,
    }


def write_env_file(env_vars: dict, output_path: str):
    """Write a shell-sourceable file with all derived variables."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        for key, value in env_vars.items():
            # Escape single quotes in values
            safe_value = str(value).replace("'", "'\\''")
            f.write(f"export {key}='{safe_value}'\n")
    print(f"Env written to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Parse OpenG2P service spec file.")
    parser.add_argument("--service-file", required=True, help="Path to service spec .txt file")
    parser.add_argument("--repo-root",    required=True, help="Root of the Docker repo (context dir)")
    parser.add_argument("--dockerfile",   default=None,  help="Override Dockerfile path")
    parser.add_argument("--output-env",   default=None,  help="Path to write shell env file")
    args = parser.parse_args()

    env_vars = parse_service_file(
        service_file=args.service_file,
        override_dockerfile=args.dockerfile,
        repo_root=args.repo_root,
    )

    if args.output_env:
        write_env_file(env_vars, args.output_env)
    else:
        for k, v in env_vars.items():
            print(f"{k}={v}")


if __name__ == "__main__":
    main()
