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
# the version check, and the script installs uv, Python, and the package into green, creates
# an empty blue venv, writes the systemd service, and starts it.
set -e
gateway_package="$1"
build="$2"
gateway_dir=/home/ubuntu/dstack
uv_version=0.13.1
python_version=3.12
uv="$gateway_dir/bin/uv"
# To prevent the uv cache grow and avoid pruning the cache, re-download all deps, which takes a few seconds.
export UV_NO_CACHE=1

mkdir -p "$gateway_dir"
cd "$gateway_dir"
if [ -f "$gateway_dir/version" ]; then
  active=$(cat "$gateway_dir/version")
else
  active=blue
fi
if [ -n "$build" ]; then
  current=$("$gateway_dir/$active/bin/python" -c 'import sys, importlib.metadata as m; print("%d.%d %s" % (sys.version_info[0], sys.version_info[1], m.version("dstack")))' 2>/dev/null || true)
  if [ "$current" = "$python_version $build" ]; then
    echo "The build $build on Python $python_version is already installed. Skipping..."
    exit 0
  fi
fi
if [ "$active" = blue ]; then
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
# The venv may contain root-owned files, e.g. bytecode written when installing the systemd
# service from it with sudo
sudo rm -rf "${gateway_dir:?}/${version:?}"
# --seed installs pip. If the dstack server is downgraded, the older server runs its own update
# script, which installs into the inactive venv with its pip, so both venvs must exist.
"$uv" venv --managed-python --seed --python "$python_version" "$gateway_dir/$version"
if [ ! -d "$gateway_dir/$active" ]; then
  "$uv" venv --managed-python --seed --python "$python_version" "$gateway_dir/$active"
fi
# Compile bytecode now, as otherwise the app compiles it on the first start, prolonging
# the downtime during the restart
"$uv" pip install --compile-bytecode --python "$gateway_dir/$version/bin/python" "$gateway_package"
sudo "$gateway_dir/$version/bin/python" -m dstack._internal.proxy.gateway.systemd install
echo "$version" > "$gateway_dir/version"
sudo systemctl daemon-reload
sudo systemctl restart dstack.gateway
echo "Update successfully completed"
