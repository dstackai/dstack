#!/bin/sh
set -e
root="$( cd -- "$(dirname "$0")" >/dev/null 2>&1; pwd -P )"

if [ -f "$root/version" ]; then
  version=$(cat "$root/version")  # blue/green
else
  version="blue"
  echo "$version" > "$root/version"
fi
"$root/$version/bin/uvicorn" dstack.gateway.main:app
