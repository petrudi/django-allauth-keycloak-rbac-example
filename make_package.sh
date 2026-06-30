#!/usr/bin/env bash
set -euo pipefail

repo_name="$(basename "$(git rev-parse --show-toplevel)")"
version="$(git describe --tags --always --dirty 2>/dev/null || git rev-parse --short HEAD)"
output_dir="dist"
output_file="${output_dir}/${repo_name}-${version}.tar.gz"

mkdir -p "${output_dir}"

# Package tracked files only, so the archive stays reproducible and clean.
git archive --format=tar --prefix="${repo_name}/" HEAD | gzip -9 > "${output_file}"

echo "Created ${output_file}"
