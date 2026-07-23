#!/usr/bin/env bash
# Installs (or updates) the HUGO systemd user service on this machine.
# Run on dgx1 as the account that runs HUGO. Safe to re-run.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
unit_dir="$HOME/.config/systemd/user"

if [[ ! -f "$HOME/.hugo_secrets" ]]; then
    echo "error: ~/.hugo_secrets not found — create it with plain KEY=VALUE lines" >&2
    echo "  (at minimum HUGO_TAVILY_API_KEY=...; no 'export' prefix)" >&2
    exit 1
fi
if grep -q "^export " "$HOME/.hugo_secrets"; then
    echo "error: ~/.hugo_secrets uses 'export KEY=...' — systemd needs plain KEY=VALUE lines" >&2
    exit 1
fi

mkdir -p "$unit_dir"
cp "$repo_root/deploy/hugo.service" "$unit_dir/hugo.service"
systemctl --user daemon-reload

echo "installed: $unit_dir/hugo.service"
echo "  start:  systemctl --user start hugo"
echo "  stop:   systemctl --user stop hugo"
echo "  logs:   journalctl --user -u hugo -f"
if ! loginctl show-user "$USER" 2>/dev/null | grep -q "Linger=yes"; then
    echo "NOTE: run 'loginctl enable-linger' once so hugo survives SSH logout."
fi
