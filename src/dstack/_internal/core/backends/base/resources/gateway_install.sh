# Installs the dstack gateway app on a fresh gateway host or updates it on an existing one.
# Usage: sh -c "$script" sh <gateway_package> <target_build>
# <target_build> is empty for unversioned packages (master builds, custom URLs).
#
# Blue/green: the app runs from one of two venvs, blue or green, named in the version file.
# The inactive venv is recreated from scratch, the dstack package is installed into it,
# and the gateway service is restarted from it.
#
# Python and the venvs are managed by uv, which is installed by the script,
# so the gateway doesn't depend on the OS Python. Changing python_version migrates existing
# gateways to the new Python on their next update.
#
# On a fresh host there is no version file and no venvs. Blue is considered active but fails
# the version check, and the script installs uv, Python, and the package into green, writes the
# systemd service, and starts it.
set -e
gateway_package="$1"
build="$2"
gateway_dir=/home/ubuntu/dstack
uv_version=0.13.1
python_version=3.12
uv="$gateway_dir/bin/uv"

mkdir -p "$gateway_dir"
cd "$gateway_dir"
if [ -f "$gateway_dir/version" ]; then
  version=$(cat "$gateway_dir/version")
else
  version=blue
fi
if [ -n "$build" ]; then
  current=$("$gateway_dir/$version/bin/python" -c 'import sys, importlib.metadata as m; print("%d.%d %s" % (sys.version_info[0], sys.version_info[1], m.version("dstack")))' 2>/dev/null || true)
  if [ "$current" = "$python_version $build" ]; then
    echo "The build $build on Python $python_version is already installed. Skipping..."
    exit 0
  fi
fi
if [ "$version" = blue ]; then
  version=green
else
  version=blue
fi
# The static binary from the uv release needs no Python to bootstrap and runs on any Linux.
# GitHub is required anyway, as uv downloads Python builds from there.
if [ "$("$uv" --version 2>/dev/null | cut -d ' ' -f 2)" != "$uv_version" ]; then
  archive=$(mktemp)
  wget -qO "$archive" "https://github.com/astral-sh/uv/releases/download/$uv_version/uv-$(uname -m)-unknown-linux-musl.tar.gz"
  mkdir -p "$gateway_dir/bin"
  tar -xzf "$archive" --strip-components=1 -C "$gateway_dir/bin"
  rm -f "$archive"
fi
"$uv" python install "$python_version"
rm -rf "${gateway_dir:?}/${version:?}"
# --seed installs pip. If the dstack server is downgraded, the older server runs its own update
# script, which calls pip in these venvs.
"$uv" venv --managed-python --seed --python "$python_version" "$gateway_dir/$version"
# Master builds and custom package URLs serve new code under the same URL, so don't reuse
# the wheel that uv cached for that URL.
"$uv" pip install --python "$gateway_dir/$version/bin/python" --refresh-package dstack "$gateway_package"
sudo "$gateway_dir/$version/bin/python" -m dstack._internal.proxy.gateway.systemd install
echo "$version" > "$gateway_dir/version"
sudo systemctl daemon-reload
sudo systemctl restart dstack.gateway
echo "Update successfully completed"
