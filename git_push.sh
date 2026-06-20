#!/bin/bash
cd /opt/pamp

git add -A

if git diff --staged --quiet; then
    echo "No changes to commit"
    exit 0
fi

CHANGED=$(git diff --staged --name-only | head -10 | tr '\n' ', ')
TIMESTAMP=$(date '+%Y-%m-%d %H:%M')
git commit -m "fix: update panel code

Changed: $CHANGED
Time: $TIMESTAMP"

git push origin main

echo "✓ Changes pushed to GitHub"
