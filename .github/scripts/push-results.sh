#!/bin/sh
# Push files to a results branch as one commit with no history.
#
#   .github/scripts/push-results.sh BRANCH "message" PATH...   (from the repository root)
#
# The branch holds only PATH... A branch made from main would carry main's workflow files, and
# GitHub refuses pushes from the Actions token that touch .github/workflows. The commit is built
# with a temporary index and commit-tree: no checkout, and the working tree is left alone.
set -eu
step=start
trap '[ $? -eq 0 ] || echo "::error title=push-results::failed at: $step"' EXIT
branch=$1
message=$2
shift 2
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
index=$(mktemp)
rm -f "$index"
step="add"
GIT_INDEX_FILE=$index git add -f -- "$@"
step="write-tree"
tree=$(GIT_INDEX_FILE=$index git write-tree)
rm -f "$index"
step="commit-tree"
commit=$(git commit-tree "$tree" -m "$message")
step="push"
# Report git's own words as an annotation, so a failure is readable without the logs.
if ! out=$(git push -f origin "$commit:refs/heads/$branch" 2>&1); then
  echo "::error title=push-results::$(printf '%s' "$out" | tr '\n' ' ' | cut -c1-900)"
  exit 1
fi
echo "pushed $* to $branch ($commit)"
