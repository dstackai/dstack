#!/bin/bash

set -e

REQUIREMENTS="
requests
pyyaml
jsonschema
dstack
jupyterlab
fastapi
streamlit
"
echo "START pip install"
export PATH="$HOME/.local/bin:$PATH"
python3 -m pip install --upgrade pip
pip3 install wheel
for req in $REQUIREMENTS; do
 pip3 install $req
done 
echo "LIST installed images"
docker image ls --all
echo "END "
