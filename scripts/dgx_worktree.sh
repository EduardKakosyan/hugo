#!/usr/bin/env bash
# Mirrors a local git worktree onto dgx1 so the same branch can be EDITED on
# the Mac and RUN on the robot's hardware, without disturbing the deployed
# ~/hugo checkout.
#
#   scripts/dgx_worktree.sh sync     # push this branch, mirror it to dgx1
#   scripts/dgx_worktree.sh use      # point hugo.service at it (hugo must be stopped)
#   scripts/dgx_worktree.sh status   # which checkout hugo.service runs right now
#   scripts/dgx_worktree.sh reset    # back to the deployed ~/hugo checkout
#   scripts/dgx_worktree.sh remove   # delete the dgx1 worktree
#
# Only ONE checkout can run at a time, and that is hardware, not policy: one
# robot, one 121GB pool, one reachy daemon that SPLITS mic frames across
# concurrent media clients instead of refusing the second one. So the branch
# is selected by overriding hugo.service in place rather than by adding a
# second unit — the wake listener gates on the literal string "hugo.service"
# (wake_listener.py), and a worktree running under any other unit name would
# leave it holding the mic alongside the voice loop: the silent half-deaf
# failure of 2026-07-23.
#
# The heavy per-service venvs are NOT duplicated per worktree. .venv-vllm
# alone is vLLM + torch; the worktree borrows all three from ~/hugo via
# HUGO_REPO_DIR (config.py resolves .venv-<svc> under repo_dir) and gets its
# own code in front of their editable installs via PYTHONPATH. Only the small
# orchestrator .venv is built per worktree, so `hugo` and the reachy daemon
# on PATH are the branch's own.
set -euo pipefail

remote="${HUGO_DGX_SSH:-hugo-dgx1}"

# Single-quoted: these are expanded by the REMOTE shell, never here.
deployed='"$HOME/hugo"'
worktree_root='$HOME/hugo-worktrees'

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$branch" == "HEAD" ]]; then
    echo "error: detached HEAD — check out a branch first" >&2
    exit 1
fi
slug="${branch//\//-}"
# Both are the literal text $HOME/hugo-worktrees/<slug>, expanded remotely.
# $wt is pre-quoted for shell command positions; $wt_path is bare, for the
# systemd drop-in (a quoted WorkingDirectory= is a parse error) and for
# copy-pasteable hints.
wt_path="$worktree_root/$slug"
wt="\"$wt_path\""

# uv is installed per-user on dgx1 and a non-interactive `ssh host cmd` shell
# does not source the profile that puts ~/.local/bin on PATH.
remote_sh() {
    ssh "$remote" "export PATH=\"\$HOME/.local/bin:\$PATH\"; set -euo pipefail; $1"
}

cmd_sync() {
    # Checked before the push: refusing afterwards would still have shipped
    # commits to origin/$branch as a side effect of a command that failed.
    remote_sh "
        # git refuses to check the same branch out twice, and its error for
        # that names a path with no hint about what to do instead.
        if [[ \"\$(git -C $deployed rev-parse --abbrev-ref HEAD)\" == '$branch' ]]; then
            echo \"error: the deployed checkout ~/hugo is already on '$branch'\" >&2
            echo '  Nothing to mirror — deploy it the normal way (git pull in ~/hugo),' >&2
            echo '  or switch to a feature branch here first.' >&2
            exit 1
        fi
    "

    if [[ -n "$(git status --porcelain)" ]]; then
        echo "note: uncommitted changes stay on this machine — only pushed commits reach dgx1" >&2
    fi
    echo "==> pushing $branch"
    git push --quiet --set-upstream origin "$branch"

    echo "==> mirroring to $remote:~/hugo-worktrees/$slug"
    remote_sh "
        git -C $deployed fetch --quiet origin '$branch'
        if [[ -d $wt ]]; then
            git -C $wt checkout --quiet '$branch'
            git -C $wt merge --quiet --ff-only 'origin/$branch'
        elif git -C $deployed show-ref --quiet --verify 'refs/heads/$branch'; then
            git -C $deployed worktree add $wt '$branch'
        else
            git -C $deployed worktree add --track -b '$branch' $wt 'origin/$branch'
        fi

        # The orchestrator venv only: small, and uv hardlinks it out of the
        # shared cache. --group robot is what puts reachy_mini (and the
        # reachy-mini-daemon binary the SDK auto-spawns) in it.
        cd $wt && uv sync --group robot

        # The three heavy venvs are shared, so a branch that changes what
        # they contain cannot be tested by borrowing them.
        for svc in vllm stt tts; do
            if ! diff -q $deployed/deploy/\$svc/requirements.txt $wt/deploy/\$svc/requirements.txt >/dev/null 2>&1; then
                echo \"WARNING: deploy/\$svc/requirements.txt differs from the deployed checkout.\"
                echo \"  This worktree borrows ~/hugo/.venv-\$svc, so that change is NOT in effect.\"
                echo \"  Build a private one:  cd $wt_path && scripts/setup_service_venv.sh \$svc\"
                echo \"  (then drop HUGO_REPO_DIR from the drop-in so it resolves here)\"
            fi
        done
    "
    echo "==> mirrored. Next: scripts/dgx_worktree.sh use"
}

cmd_use() {
    echo "==> pointing hugo.service at $slug"
    remote_sh "
        if [[ ! -d $wt ]]; then
            echo 'error: no such worktree — run: scripts/dgx_worktree.sh sync' >&2
            exit 1
        fi
        state=\$(systemctl --user is-active hugo.service || true)
        if [[ \"\$state\" != 'inactive' && \"\$state\" != 'failed' ]]; then
            echo \"error: hugo.service is \$state — stop it first (systemctl --user stop hugo)\" >&2
            echo '  Repointing a live unit orphans the running stack from its unit.' >&2
            exit 1
        fi

        mkdir -p \"\$HOME/.config/systemd/user/hugo.service.d\"
        cat > \"\$HOME/.config/systemd/user/hugo.service.d/10-worktree.conf\" <<EOF
# Written by scripts/dgx_worktree.sh — remove with 'dgx_worktree.sh reset'.
# hugo.service runs a worktree instead of the deployed ~/hugo checkout.
[Service]
WorkingDirectory=$wt_path
# Borrow the deployed .venv-vllm/.venv-stt/.venv-tts (config.repo_dir)...
Environment=HUGO_REPO_DIR=%h/hugo
# ...but put THIS branch's code ahead of their editable installs. PYTHONPATH
# precedes site-packages and the installs are plain .pth path entries, so it
# wins; process_manager passes the environment through to the servers.
Environment=PYTHONPATH=$wt_path/src
Environment=PATH=$wt_path/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=
ExecStart=$wt_path/.venv/bin/hugo start
EOF
        systemctl --user daemon-reload
        echo \"active checkout: \$(systemctl --user show hugo.service -p WorkingDirectory --value)\"
    "
    echo "==> start it as usual: ssh $remote systemctl --user start hugo"
}

cmd_reset() {
    echo "==> restoring the deployed checkout"
    remote_sh "
        state=\$(systemctl --user is-active hugo.service || true)
        if [[ \"\$state\" != 'inactive' && \"\$state\" != 'failed' ]]; then
            echo \"error: hugo.service is \$state — stop it first (systemctl --user stop hugo)\" >&2
            exit 1
        fi
        rm -f \"\$HOME/.config/systemd/user/hugo.service.d/10-worktree.conf\"
        rmdir \"\$HOME/.config/systemd/user/hugo.service.d\" 2>/dev/null || true
        systemctl --user daemon-reload
        echo \"active checkout: \$(systemctl --user show hugo.service -p WorkingDirectory --value)\"
    "
}

cmd_status() {
    remote_sh "
        echo \"hugo.service:     \$(systemctl --user is-active hugo.service || true)\"
        echo \"hugo-wake:        \$(systemctl --user is-active hugo-wake.service || true)\"
        echo \"active checkout:  \$(systemctl --user show hugo.service -p WorkingDirectory --value)\"
        echo
        echo 'worktrees:'
        git -C $deployed worktree list
        echo
        free -g | head -2
    "
}

cmd_remove() {
    echo "==> removing $remote:~/hugo-worktrees/$slug"
    remote_sh "
        active=\$(systemctl --user show hugo.service -p WorkingDirectory --value)
        if [[ \"\$active\" == $wt ]]; then
            echo 'error: hugo.service still points here — run: scripts/dgx_worktree.sh reset' >&2
            exit 1
        fi
        git -C $deployed worktree remove --force $wt
        echo 'removed'
    "
}

case "${1:-}" in
    sync) cmd_sync ;;
    use) cmd_use ;;
    reset) cmd_reset ;;
    status) cmd_status ;;
    remove) cmd_remove ;;
    *)
        echo "usage: scripts/dgx_worktree.sh {sync|use|status|reset|remove}" >&2
        echo "  branch: $branch  ->  $remote:~/hugo-worktrees/$slug" >&2
        exit 1
        ;;
esac
