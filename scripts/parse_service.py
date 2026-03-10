#!/usr/bin/env python3
"""
parse_service.py — Parses an OpenG2P service spec file and emits a shell-sourceable
env file plus the adapters.requirements.txt consumed by the Dockerfiles.

This is a direct Python equivalent of the "Read service file and prepare adapters
requirements" step in docker-build.yml.

Supports two dependency syntaxes in the service spec file:

  Remote (fetched from GitHub at pip-install time):
    git://BRANCH_OR_TAG//https://github.com/org/repo#subdirectory=pkg

  Local (package directory already checked out on this machine — full path):
    /home/puneet/repos/openg2p-g2pconnect-common-lib/openg2p-g2pconnect-mapper-lib

  For local entries the directory is copied into <repo_root>/local_deps/<dir_name>/
  inside the Docker build context, and the requirements entry becomes:
    ./local_deps/<dir_name>
  so pip installs it from the local source tree rather than fetching from GitHub.

Usage (called by build.sh, but can also be run directly):
    python3 parse_service.py \\
        --service-file staff-portal-api/farmer-develop.txt \\
        --repo-root    /path/to/repo \\
        [--dockerfile  staff-portal-api/Dockerfile] \\
        [--output-env  /tmp/service_env.sh]
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_local_path(val: str) -> bool:
    """Return True if the line looks like a local filesystem path."""
    return val.startswith("/") or val.startswith("./") or val.startswith("../")


def _resolve_local_dep(val: str, repo_root: str) -> tuple[str, str]:
    """
    Given a plain local path like:
        /home/puneet/repos/openg2p-g2pconnect-common-lib/openg2p-g2pconnect-mapper-lib

    Copy that directory into <repo_root>/local_deps/<dir_name>/ so it sits inside
    the Docker build context, and return (pip_requirement_line, dir_name).

    The pip requirement line will be  ./local_deps/<dir_name>
    which pip can install as a local package.
    """
    src = os.path.abspath(val.strip())
    pkg_name = os.path.basename(src)
    local_deps_root = os.path.join(repo_root, "local_deps")
    dest = os.path.join(local_deps_root, pkg_name)

    if not os.path.exists(src):
        print(f"ERROR: Local dependency path does not exist: {src}", file=sys.stderr)
        sys.exit(1)

    # Always refresh the copy so stale files don't sneak in
    if os.path.exists(dest):
        shutil.rmtree(dest)
    print(f"  [local] Copying {src}  →  local_deps/{pkg_name}/")
    shutil.copytree(src, dest)

    return f"./local_deps/{pkg_name}", pkg_name


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

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
        service_dir = os.path.dirname(service_file)
        candidate = os.path.join(service_dir, "Dockerfile")
        if os.path.exists(candidate):
            dockerfile = candidate

    if not dockerfile and len(lines) > 1 and lines[1].startswith("#!"):
        dockerfile = lines[1].lstrip("#!").strip()

    if not dockerfile:
        print(
            f"Error: Could not determine Dockerfile for {service_file}. "
            "Pass --dockerfile explicitly.",
            file=sys.stderr,
        )
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Wipe local_deps from any previous run so nothing stale carries over
    # -----------------------------------------------------------------------
    local_deps_root = os.path.join(repo_root, "local_deps")
    if os.path.exists(local_deps_root):
        shutil.rmtree(local_deps_root)

    # -----------------------------------------------------------------------
    # Dependency / git line parsing
    # -----------------------------------------------------------------------
    deps = []        # lines written to adapters.requirements.txt
    local_pkgs = []  # package names sourced locally (for logging)
    repo_url = ""
    git_branch = ""

    for line in lines:
        if line.startswith("#"):
            continue
        val = line.strip()
        if not val:
            continue

        # ------------------------------------------------------------------
        # Case 1: local path  (/abs/path/to/package  or  ./rel/path)
        # ------------------------------------------------------------------
        if _is_local_path(val):
            pip_line, pkg_name = _resolve_local_dep(val, repo_root)
            deps.append(pip_line)
            local_pkgs.append(pkg_name)
            continue

        # ------------------------------------------------------------------
        # Case 2: remote git dep   git://TAG//URL[#subdirectory=...]
        # ------------------------------------------------------------------
        m = re.match(r"git://([^/]+)//(.+)", val)
        if m:
            tag = m.group(1)
            url_full = m.group(2)
            # Capture first remote git dep as primary repo/branch for Dockerfile ARGs
            if not repo_url:
                repo_url = url_full.split("#")[0] if "#" in url_full else url_full
                git_branch = tag
            if "#" in url_full:
                base, frag = url_full.split("#", 1)
                deps.append(f"git+{base}@{tag}#{frag}")
            else:
                deps.append(f"git+{url_full}@{tag}")
            continue

        # ------------------------------------------------------------------
        # Case 3: plain pip requirement  (e.g. requests==2.31.0)
        # ------------------------------------------------------------------
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
    if local_pkgs:
        print(f"Local packages staged into local_deps/: {', '.join(local_pkgs)}")

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


# ---------------------------------------------------------------------------
# Env-file writer
# ---------------------------------------------------------------------------

def write_env_file(env_vars: dict, output_path: str):
    """Write a shell-sourceable file with all derived variables."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        for key, value in env_vars.items():
            safe_value = str(value).replace("'", "'\\''")
            f.write(f"export {key}='{safe_value}'\n")
    print(f"Env written to: {output_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

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
