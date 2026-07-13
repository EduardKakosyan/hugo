#!/usr/bin/env bash
# Creates an isolated venv for one model-serving subprocess (see docs/adr/0005)
# and installs the hugo package (editable) plus that service's own pinned
# heavy dependencies into it, so servers/*.py stays importable everywhere
# without forcing every model library into one shared environment.
#
# Usage: scripts/setup_service_venv.sh <service>   (service = a directory under deploy/)
set -euo pipefail

service="${1:?usage: setup_service_venv.sh <service>}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
requirements="$repo_root/deploy/$service/requirements.txt"
venv_dir="$repo_root/.venv-$service"

if [[ ! -f "$requirements" ]]; then
    echo "no such service: $requirements not found" >&2
    exit 1
fi

uv venv --python 3.12 "$venv_dir"
uv pip install --python "$venv_dir/bin/python" -e "$repo_root"
uv pip install --python "$venv_dir/bin/python" -r "$requirements"

echo "ready: $venv_dir/bin/python -m hugo.servers.${service}_server"
