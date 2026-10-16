#!/bin/bash
#
# PAMP auto-commit/push watcher — guarded + debounced.
#
# Normal (daemon) mode: watches /opt/pamp for changes, waits for edits to
# settle (debounce), then makes ONE commit for the whole batch and pushes
# ONLY the "main" branch to origin. Never pushes tags or other branches,
# never force-pushes.
#
# Before every commit it refuses (and unstages) anything that looks like a
# DB dump, an env/secret file, an oversized file, or content matching a
# common secret pattern — so a leak like the backups/*.sql incident can't
# happen again even if .gitignore is ever incomplete.
#
# Modes (first argument):
#   (none)          daemon mode — what the systemd unit runs
#   --once          run a single debounced-commit check and exit (for testing)
#   --force-sync    one-time maintenance push: `git push --force-with-lease
#                   origin main` + `git push origin v1.5.3`, then exit.
#                   Never run automatically — only by explicit invocation.

set -u
: "${PAMP_REPO_DIR:=/opt/pamp}"
cd "$PAMP_REPO_DIR" || exit 1

LOG_FILE="$PAMP_REPO_DIR/logs/autopush.log"
LOCK_FILE="$PAMP_REPO_DIR/.autopush.lock"
DEBOUNCE_SECONDS=60
MAX_FILE_BYTES=$((5 * 1024 * 1024))   # 5 MB

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG_FILE"
}

# Paths that must never be committed, regardless of .gitignore's current
# state — defense-in-depth in case a secret/dump ever lands somewhere
# .gitignore doesn't (yet) cover.
is_forbidden_path() {
    case "$1" in
        .env.example) return 1 ;;  # explicitly allowed: placeholder template, no real secrets
        *.sql|*.sql.gz|*.dump|backups/*|.env|*.env|.env.*|*.pem|*.key) return 0 ;;
    esac
    return 1
}

# Scan the STAGED diff only (never the working tree at large) for common
# secret shapes: KEY=value env-style assignments, private-key headers,
# Telegram-bot-token shape, GitHub PAT shapes.
has_secret_pattern() {
    git diff --staged -U0 -- . ':!.env.example' 2>/dev/null | grep -aE \
        -e '^\+.*[A-Z_]*(PASSWORD|SECRET_KEY|BOT_TOKEN|API_KEY|ACCESS_TOKEN)[[:space:]]*=[[:space:]]*[^[:space:]]{4,}' \
        -e '^\+.*-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----' \
        -e '^\+.*[0-9]{8,10}:[A-Za-z0-9_-]{30,}' \
        -e '^\+.*ghp_[A-Za-z0-9]{20,}' \
        -e '^\+.*github_pat_[A-Za-z0-9_]{20,}' \
        -q
}

# Stage everything, run the safety guards, and — only if all of them pass —
# make exactly one commit for the whole batch and push main. Any refusal
# unstages cleanly and logs why; nothing is ever pushed on a refusal.
run_once() {
    cd "$PAMP_REPO_DIR" || return 1
    git add -A

    if git diff --staged --quiet; then
        return 0   # nothing to do
    fi

    local staged bad_path="" big_file="" f size
    staged=$(git diff --staged --name-only)

    while IFS= read -r f; do
        [ -z "$f" ] && continue
        if is_forbidden_path "$f"; then bad_path="$f"; break; fi
    done <<< "$staged"
    if [ -n "$bad_path" ]; then
        git reset -q HEAD -- .
        log "REFUSED: forbidden path staged ($bad_path) — unstaged, nothing committed/pushed."
        return 1
    fi

    while IFS= read -r f; do
        [ -z "$f" ] && continue
        [ -f "$f" ] || continue
        size=$(stat -c%s "$f" 2>/dev/null || echo 0)
        if [ "$size" -gt "$MAX_FILE_BYTES" ]; then big_file="$f (${size} bytes)"; break; fi
    done <<< "$staged"
    if [ -n "$big_file" ]; then
        git reset -q HEAD -- .
        log "REFUSED: staged file too large ($big_file) — unstaged, nothing committed/pushed."
        return 1
    fi

    if has_secret_pattern; then
        git reset -q HEAD -- .
        log "REFUSED: staged content matched a secret pattern — unstaged, nothing committed/pushed."
        return 1
    fi

    local changed_count summary timestamp
    changed_count=$(printf '%s\n' "$staged" | grep -c .)
    summary=$(printf '%s\n' "$staged" | head -5 | tr '\n' ' ')
    [ "$changed_count" -gt 5 ] && summary="$summary ...(+$((changed_count - 5)) more)"
    timestamp=$(date '+%Y-%m-%d %H:%M')

    if ! git commit -q -m "auto: code update at $timestamp

Files ($changed_count): $summary"; then
        log "COMMIT FAILED — nothing pushed."
        return 1
    fi
    log "COMMIT ok: $changed_count file(s): $summary"

    if git push origin main -q 2>>"$LOG_FILE"; then
        log "PUSH ok: main"
    else
        log "PUSH FAILED: main (commit kept locally — HEAD still differs from origin, will be retried by the next successful push)"
        return 1
    fi
}

# One-time maintenance push. Never called from the normal watch loop —
# only by explicit `--force-sync` invocation.
force_sync_once() {
    cd "$PAMP_REPO_DIR" || return 1
    log "FORCE-SYNC: starting (main --force-with-lease, then tag v1.5.3)"
    if git push --force-with-lease origin main 2>>"$LOG_FILE"; then
        log "FORCE-SYNC: main pushed (force-with-lease) ok"
    else
        log "FORCE-SYNC: main push FAILED"
        return 1
    fi
    if git push origin v1.5.3 2>>"$LOG_FILE"; then
        log "FORCE-SYNC: tag v1.5.3 pushed ok"
    else
        log "FORCE-SYNC: tag v1.5.3 push failed (may already exist on remote — check log above)"
    fi
}

case "${1:-}" in
    --once)
        run_once
        exit $?
        ;;
    --force-sync)
        force_sync_once
        exit $?
        ;;
esac

# ── daemon mode (what systemd runs) ─────────────────────────────────────
log "watch_and_push.sh starting in daemon mode (pid $$)"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    log "another instance holds the lock — exiting"
    exit 1
fi

EXCLUDE='(__pycache__|\.pyc|\.git|staticfiles|\.log|backups/|logs/|\.autopush)'

while inotifywait -r -e modify,create,delete,move --exclude "$EXCLUDE" "$PAMP_REPO_DIR" 2>/dev/null; do
    # Debounce: keep resetting the timer for as long as new events keep
    # arriving; once DEBOUNCE_SECONDS pass with no new event, proceed.
    while inotifywait -r -t "$DEBOUNCE_SECONDS" -e modify,create,delete,move --exclude "$EXCLUDE" "$PAMP_REPO_DIR" >/dev/null 2>&1; do
        :
    done
    run_once
done
