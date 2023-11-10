#!/bin/bash

set -e

IMAGES="
 dstackai/base:py3.11-${IMAGE_VERSION}
 dstackai/base:py3.10-${IMAGE_VERSION}
 dstackai/base:py3.9-${IMAGE_VERSION}
 dstackai/base:py3.8-${IMAGE_VERSION}
"
echo "START pull image"
for img in $IMAGES; do
 docker pull --platform linux/amd64 $img
done 
echo "LIST installed images"
docker image ls --all
echo "END "
