#!/bin/bash

set -e

IMAGES="
 dstackai/miniforge:3.10
 dstackai/miniforge:3.9
 dstackai/miniforge:3.8
 dstackai/miniforge:3.7
"
echo "START pull image"
for img in $IMAGES; do
 docker pull --platform linux/amd64 $img
done 
echo "LIST installed images"
docker image ls --all
echo "END "
