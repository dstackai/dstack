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

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
	 cuda-drivers=$CUDA_DRIVERS_VERSION

sudo DEBIAN_FRONTEND=noninteractive apt-get install -y curl
NVDOCKER_DISTRO=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$NVDOCKER_DISTRO/nvidia-docker.list \
	| sudo tee /etc/apt/sources.list.d/nvidia-docker.list
curl -s -L https://nvidia.github.io/nvidia-container-runtime/experimental/$NVDOCKER_DISTRO/nvidia-container-runtime.list \
	| sudo tee /etc/apt/sources.list.d/nvidia-container-runtime.list
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends nvidia-docker2

echo "*****************************************************************************"
echo "*** Reboot your computer and verify that the NVIDIA graphics driver can   ***"
echo "*** be loaded.                                                            ***"
echo "*****************************************************************************"


