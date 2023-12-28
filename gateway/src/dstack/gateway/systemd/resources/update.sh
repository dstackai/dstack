#!/bin/sh
set -e
root="$( cd -- "$(dirname "$0")" >/dev/null 2>&1; pwd -P )"

if [ "$#" -eq 0 ]; then
    echo "Error: Missing wheel URL"
    exit 1
fi

if [ -f "$root/version" ]; then
  version=$(cat "$root/version")  # blue/green
else
  version="blue"
fi

# flip the version
if [ "$version" = "blue" ]; then
  version="green"
else
  version="blue"
fi

"$root/$version/bin/pip" install "$1"
# sudo "$root/$version/bin/python" -m dstack.gateway.systemd install
echo "$version" > "$root/version"
# sudo systemctl daemon-reload
sudo systemctl restart dstack.gateway
