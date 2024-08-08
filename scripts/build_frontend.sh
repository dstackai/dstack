#!/bin/sh

script_path="$(realpath $0)"
root_dir="$(dirname $(dirname $script_path))"

cd $root_dir
cd frontend
npm install
npm run build
rm -rf ../src/dstack/_internal/server/statics
cp -a build ../src/dstack/_internal/server/statics
