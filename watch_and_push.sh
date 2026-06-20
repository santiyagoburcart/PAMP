#!/bin/bash
cd /opt/pamp
echo "Watching for file changes..."

while inotifywait -r -e modify,create,delete,move \
    --exclude '(__pycache__|\.pyc|\.git|staticfiles|\.log)' \
    /opt/pamp 2>/dev/null; do

    sleep 3

    cd /opt/pamp
    git add -A

    if ! git diff --staged --quiet; then
        CHANGED=$(git diff --staged --name-only | head -5 | tr '\n' ' ')
        TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
        git commit -m "auto: code update at $TIMESTAMP

Files: $CHANGED"
        git push origin main
        echo "✓ Pushed at $TIMESTAMP: $CHANGED"
    fi
done
