#!/bin/bash

set -e

IMAGES="
 dstackai/miniconda:3.10
 dstackai/miniconda:3.9
 dstackai/miniconda:3.8
 dstackai/miniconda:3.7
"
echo "START pull image"
for img in $IMAGES; do
 docker pull $img
done 
echo "LIST installed images"
docker image ls --all
echo "END "
