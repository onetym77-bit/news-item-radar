#!/usr/bin/env bash
set -euo pipefail

branch="${1:-main}"
max_attempts="${2:-5}"

if ! [[ "$max_attempts" =~ ^[1-9][0-9]*$ ]]; then
  echo "max_attempts must be a positive integer: $max_attempts" >&2
  exit 2
fi

for attempt in $(seq 1 "$max_attempts"); do
  git fetch origin "$branch"

  if ! git rebase "origin/$branch"; then
    git rebase --abort || true
    echo "Remote changes conflict with this workflow output; refusing to overwrite $branch." >&2
    exit 1
  fi

  if git push origin "HEAD:$branch"; then
    echo "Pushed workflow output to $branch on attempt $attempt."
    exit 0
  fi

  echo "Remote $branch moved during push; retrying ($attempt/$max_attempts)." >&2
  sleep $((attempt * 2))
done

echo "Remote $branch kept moving; refusing to overwrite it after $max_attempts attempts." >&2
exit 1
