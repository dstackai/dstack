#!/bin/bash

set -e

sudo DEBIAN_FRONTEND=noninteractive apt-get install -y curl
NVDOCKER_DISTRO=$(. /etc/os-release;echo $ID$VERSION_ID)

curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$NVDOCKER_DISTRO/nvidia-docker.list \
	| sudo tee /etc/apt/sources.list.d/nvidia-docker.list
curl -s -L https://nvidia.github.io/nvidia-container-runtime/experimental/$NVDOCKER_DISTRO/nvidia-container-runtime.list \
	| sudo tee /etc/apt/sources.list.d/nvidia-container-runtime.list

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends nvidia-docker2
