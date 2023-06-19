#!/bin/sh

script_path="$(realpath $0)"
root_dir="$(dirname $(dirname $script_path))"

cd hub
npm run build
rm -rf ../cli/dstack/_internal/hub/statics
cp -r build ../cli/dstack/_internal/hub/statics
