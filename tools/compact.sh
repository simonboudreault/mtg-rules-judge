#!/usr/bin/env bash
# Keep the repository small enough to clone quickly.
#
# Every card-database rebuild adds a ~9 MB gzip blob that git can't delta-compress,
# and everyone who installs the plugin clones the whole repository, history included.
# This script, run by the workflow after each data release:
#
#   1. deletes GitHub releases (and their tags) beyond the newest KEEP_RELEASES;
#   2. when the packed history exceeds COMPACT_THRESHOLD_MB, replaces `main` with a
#      single commit holding the current files, force-pushes it, and re-points the
#      remaining release tags at that commit so no old history stays reachable.
#
# Needs a full clone (actions/checkout with fetch-depth: 0) and GH_TOKEN for gh.
# Set COMPACT_DRY_RUN=1 to print what would happen without changing anything.
set -euo pipefail

THRESHOLD_MB="${COMPACT_THRESHOLD_MB:-150}"
KEEP="${KEEP_RELEASES:-5}"
DRY="${COMPACT_DRY_RUN:-0}"

run() { if [ "$DRY" = "1" ]; then echo "[dry-run] $*"; else "$@"; fi; }

# ---- 1. prune old releases -------------------------------------------------
mapfile -t releases < <(gh release list --limit 200 --exclude-drafts --json tagName -q '.[].tagName')
echo "Releases: ${#releases[@]} (keeping newest $KEEP)"
for tag in "${releases[@]:$KEEP}"; do
  echo "  deleting release $tag"
  run gh release delete "$tag" --cleanup-tag --yes
done
kept=("${releases[@]:0:$KEEP}")

# ---- 2. compact history when it gets heavy ---------------------------------
if git rev-parse --is-shallow-repository | grep -q true; then
  echo "Shallow clone: can't measure history, skipping compaction" >&2
  exit 0
fi
# loose objects + packs (a fresh clone is all packs; a local checkout may be all loose)
size_kb=$(git count-objects -v | awk '/^size(-pack)?:/ {s += $2} END {print s}')
size_mb=$((size_kb / 1024))
echo "Packed history: ${size_mb} MB (threshold ${THRESHOLD_MB} MB)"
if [ "$size_mb" -lt "$THRESHOLD_MB" ]; then
  exit 0
fi

echo "Compacting history to a single snapshot commit"
if [ -z "$(git config user.email)" ]; then
  git config user.name "github-actions[bot]"
  git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
fi
snapshot_date=$(date -u +%F)
run git checkout -q --orphan compacted
run git add -A
run git commit -q -m "Compact history: snapshot of $snapshot_date" \
  -m "Older commits were dropped to keep the repository quick to clone; every released version's zip is still on the Releases page."
run git branch -D main
run git branch -m main
run git push --force origin main

# Re-point surviving release tags at the snapshot and drop every other remote tag,
# so nothing keeps the old commits reachable.
for tag in "${kept[@]}"; do
  run git tag -f "$tag" main
done
mapfile -t remote_tags < <(git ls-remote --tags --refs origin | awk '{sub("refs/tags/", "", $2); print $2}')
for tag in "${remote_tags[@]}"; do
  keep_it=0
  for k in "${kept[@]}"; do [ "$tag" = "$k" ] && keep_it=1; done
  if [ "$keep_it" = "0" ]; then
    echo "  deleting stray tag $tag"
    run git push --delete origin "$tag"
  fi
done
run git push --force origin --tags
echo "Done. Local clones must run: git fetch origin && git reset --hard origin/main"
