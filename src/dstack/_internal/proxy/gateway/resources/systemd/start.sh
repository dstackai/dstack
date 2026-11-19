#!/bin/sh
set -e
root="$( cd -- "$(dirname "$0")" >/dev/null 2>&1; pwd -P )"

if [ -f "$root/version" ]; then
  version=$(cat "$root/version")  # blue/green
else
  version="blue"
  echo "$version" > "$root/version"
fi
# Without the timeout, uvicorn waits for all open streams to end before it shuts the app down.
"$root/$version/bin/uvicorn" dstack._internal.proxy.gateway.main:app --loop uvloop --timeout-graceful-shutdown 10
