#!/usr/bin/env python3
import os
import sys
import re
import argparse
import subprocess
from datetime import datetime

def parse_service_file(service_file, override_dockerfile=None):
    if not os.path.exists(service_file):
        print(f"Error: Service file not found: {service_file}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading service file: {service_file}")
    with open(service_file, 'r') as f:
        lines = [line.strip() for line in f if line.strip()]

    if not lines or not lines[0].startswith('#!'):
        print("Error: Invalid file format. First line must start with #!IMAGE_ID", file=sys.stderr)
        sys.exit(1)

    # Line 1: Image ID
    image_id = lines[0].lstrip('#!').strip()
    print(f"Target Image ID: {image_id}")

    # Dockerfile resolution
    dockerfile = override_dockerfile
    
    # 1. Look for Dockerfile in same directory as service file
    if not dockerfile:
        service_dir = os.path.dirname(service_file)
        candidate = os.path.join(service_dir, 'Dockerfile')
        if os.path.exists(candidate):
            dockerfile = candidate

    # 2. Legacy check: line 2 starts with #!
    if not dockerfile and len(lines) > 1 and lines[1].startswith('#!'):
        dockerfile = lines[1].lstrip('#!').strip()
    
    if not dockerfile:
        # Fallback to just "Dockerfile" in current dir
        if os.path.exists("Dockerfile"):
             dockerfile = "Dockerfile"
        else:
            print("Error: Dockerfile path could not be determined.", file=sys.stderr)
            sys.exit(1)
            
    print(f"Using Dockerfile: {dockerfile}")

    # Parse dependencies
    deps = []
    for line in lines:
        if line.startswith('#!'): continue
        if line.startswith('#'): continue
        
        val = line.strip()
        
        # Parse git://TAG//URL
        m = re.match(r'git://([^/]+)//(.+)', val)
        if m:
            tag = m.group(1)
            url_full = m.group(2)
            if '#' in url_full:
                base, frag = url_full.split('#', 1)
                req = f"git+{base}@{tag}#{frag}"
            else:
                req = f"git+{url_full}@{tag}"
            deps.append(req)
        else:
            if val:
                deps.append(val)

    return image_id, dockerfile, deps

def main():
    parser = argparse.ArgumentParser(description="Build OpenG2P Docker image locally using spec file.")
    parser.add_argument("service_file", nargs='?', default="staff-portal-api/farmer-develop.txt", help="Path to the service spec file (default: staff-portal-api/farmer-develop.txt)")
    parser.add_argument("--dockerfile", help="Path to Dockerfile (optional)")
    parser.add_argument("--push", action="store_true", help="Push image to registry after build")
    parser.add_argument("--no-cache", action="store_true", help="Do not use cache when building")

    args = parser.parse_args()

    image_id, dockerfile, deps = parse_service_file(args.service_file, args.dockerfile)

    # Write adapters.requirements.txt
    req_file = "adapters.requirements.txt"
    with open(req_file, 'w') as f:
        f.write('\n'.join(deps))
    
    print(f"\nGenerated {req_file}:")
    print('\n'.join(deps))
    print("-" * 30)

    # Git info (for labels)
    try:
        commit_hash = subprocess.check_output(['git', '--no-pager', 'log', '-1', '--pretty=format:%H']).decode('utf-8').strip()
    except:
        commit_hash = "unknown"
        
    created = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Labels
    vendor = image_id.split('/')[0] if '/' in image_id else "unknown"
    try:
        title = image_id.split('/')[1].split(':')[0]
    except:
        title = image_id
    
    version = "latest"
    if ':' in image_id:
        version = image_id.split(':')[-1]

    # Build Command
    cmd = [
        "docker", "build",
        "-f", dockerfile,
        "-t", image_id,
        "--label", f"org.opencontainers.image.created={created}",
        "--label", f"org.opencontainers.image.revision={commit_hash}",
        "--label", f"org.opencontainers.image.vendor={vendor}",
        "--label", f"org.opencontainers.image.title={title}",
        "--label", f"org.opencontainers.image.version={version}",
        "."
    ]

    if args.no_cache:
        cmd.insert(2, "--no-cache")

    print(f"\nRunning build command:\n{' '.join(cmd)}\n")
    
    try:
        subprocess.check_call(cmd)
        print(f"\n✅ Build successful! Image: {image_id}")
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Build failed with exit code {e.returncode}")
        sys.exit(e.returncode)

    if args.push:
        print(f"Pushing image {image_id}...")
        subprocess.check_call(["docker", "push", image_id])

if __name__ == "__main__":
    main()
