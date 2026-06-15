#!/bin/bash

set -e

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y build-essential
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y linux-headers-$(uname -r)

ARCH=$(uname -m)
CUDA_DISTRO=$(. /etc/os-release;echo $ID$VERSION_ID | sed -e 's/\.//g')

# based on https://docs.nvidia.com/datacenter/tesla/driver-installation-guide/ubuntu.html
wget https://developer.download.nvidia.com/compute/cuda/repos/$CUDA_DISTRO/$ARCH/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
rm cuda-keyring_1.1-1_all.deb

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    nvidia-driver-pinning-$CUDA_DRIVERS_VERSION

sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    nvidia-open \
    nvidia-fabricmanager \
    datacenter-gpu-manager-4-core datacenter-gpu-manager-4-proprietary datacenter-gpu-manager-exporter
sudo systemctl enable nvidia-fabricmanager
