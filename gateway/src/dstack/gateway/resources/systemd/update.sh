#!/bin/sh
set -e
root="$( cd -- "$(dirname "$0")" >/dev/null 2>&1; pwd -P )"

# usage: ./update.sh <wheel_url> <build>
if [ "$#" -eq 0 ]; then
    echo "Error: Missing wheel URL"
    exit 1
elif [ "$#" -eq 1 ]; then
    echo "Error: Missing build version"
    exit 1
fi

if [ -f "$root/version" ]; then
  version=$(cat "$root/version")  # blue/green
else
  version="blue"
fi

# check the current build version
current_build=$($root/$version/bin/pip show dstack-gateway | grep Version | awk '{print $2}')
if [ "$current_build" = "$2" ]; then
  echo "The build $2 is already installed. Skipping..."
  exit 0
fi

# flip the version
if [ "$version" = "blue" ]; then
  version="green"
else
  version="blue"
fi

"$root/$version/bin/pip" uninstall -y dstack-gateway dstack
"$root/$version/bin/pip" cache remove dstack
"$root/$version/bin/pip" install "$1"
sudo "$root/$version/bin/python" -m dstack.gateway.systemd install
echo "$version" > "$root/version"
sudo systemctl daemon-reload
sudo systemctl restart dstack.gateway

echo "Update successfully completed"
