#!/bin/sh
# Push files to a results branch as one commit with no history.
#
#   .github/scripts/push-results.sh BRANCH "message" PATH...   (from the repository root)
#
# The branch holds only PATH... A branch made from main would carry main's workflow files, and
# GitHub refuses pushes from the Actions token that touch .github/workflows.
set -eu
trap '[ $? -eq 0 ] || echo "::error title=push-results::failed near: $last"' EXIT
last=start
branch=$1
message=$2
shift 2
tmp=$(mktemp -d)
for p in "$@"; do
  mkdir -p "$tmp/$(dirname "$p")"
  cp -R "$p" "$tmp/$p"
done
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
last="checkout --orphan"
git checkout -q --orphan "results-$$"
git rm -rq --cached . >/dev/null
for p in "$@"; do
  mkdir -p "$(dirname "$p")"
  rm -rf "$p"
  cp -R "$tmp/$p" "$p"
  git add -f "$p"
done
last="commit"
git commit -q -m "$message"
# Report git's own words as an annotation, so a failure is readable without the logs.
if ! out=$(git push -f origin "HEAD:refs/heads/$branch" 2>&1); then
  echo "::error title=push-results::$(printf '%s' "$out" | tr '\n' ' ' | cut -c1-900)"
  exit 1
fi
echo "pushed $* to $branch"
