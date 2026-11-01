#!/bin/bash
# Run a command and surface its result as a GitHub annotation (readable through the API even when
# job logs aren't): on failure an error with the last lines of output, on success a notice with
# the last line. Output still streams to the log.
#
#   .github/scripts/annotate.sh "title" command args...
set -uo pipefail
title=$1
shift
log=$(mktemp)
"$@" 2>&1 | tee "$log"
status=${PIPESTATUS[0]}
flat() { tail -c "$1" "$log" | tr '\n' ' ' | tr -s ' '; }
if [ "$status" -ne 0 ]; then
  echo "::error title=$title::exit $status: $(flat 900)"
else
  echo "::notice title=$title::$(tail -n 1 "$log" | cut -c1-400)"
fi
exit "$status"
