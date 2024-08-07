#!/bin/bash

set -e

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y linux-headers-$(uname -r)

ARCH=$(uname -m)
CUDA_DISTRO=$(. /etc/os-release;echo $ID$VERSION_ID | sed -e 's/\.//g')

# based on https://docs.nvidia.com/datacenter/tesla/tesla-installation-notes/index.html#ubuntu-lts
wget https://developer.download.nvidia.com/compute/cuda/repos/$CUDA_DISTRO/$ARCH/cuda-keyring_1.0-1_all.deb
sudo dpkg -i cuda-keyring_1.0-1_all.deb
rm cuda-keyring_1.0-1_all.deb

CUDA_BRANCH=$(cut -d '.' -f 1 <<< "$CUDA_DRIVERS_VERSION")
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    cuda-drivers-$CUDA_BRANCH=$CUDA_DRIVERS_VERSION \
    nvidia-fabricmanager-$CUDA_BRANCH=$CUDA_DRIVERS_VERSION
sudo systemctl enable nvidia-fabricmanager
