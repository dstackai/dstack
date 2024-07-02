#!/bin/bash

# based on https://learn.microsoft.com/en-us/azure/virtual-machines/linux/n-series-driver-setup#install-grid-drivers-on-nv-or-nvv3-series-vms

set -e

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install build-essential linux-azure -y

wget --no-verbose -O NVIDIA-Linux-x86_64-grid.run \
    https://download.microsoft.com/download/8/d/a/8da4fb8e-3a9b-4e6a-bc9a-72ff64d7a13c/NVIDIA-Linux-x86_64-535.161.08-grid-azure.run
chmod +x NVIDIA-Linux-x86_64-grid.run
sudo ./NVIDIA-Linux-x86_64-grid.run --silent --disable-nouveau
rm NVIDIA-Linux-x86_64-grid.run

sudo cat /etc/nvidia/gridd.conf.template |
    grep -v "FeatureType=" |
    grep -v "IgnoreSP=" |
    grep -v "EnableUI=" |
    sudo tee /etc/nvidia/gridd.conf > /dev/null
echo "IgnoreSP=FALSE" | sudo tee --append /etc/nvidia/gridd.conf > /dev/null
echo "EnableUI=FALSE" | sudo tee --append /etc/nvidia/gridd.conf > /dev/null
