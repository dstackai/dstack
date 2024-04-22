#!/bin/bash

# based on https://learn.microsoft.com/en-us/azure/virtual-machines/linux/n-series-driver-setup#install-grid-drivers-on-nv-or-nvv3-series-vms

set -e

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install build-essential linux-azure -y

wget --no-verbose -O NVIDIA-Linux-x86_64-grid.run \
    https://download.microsoft.com/download/1/4/4/14450d0e-a3f2-4b0a-9bb4-a8e729e986c4/NVIDIA-Linux-x86_64-535.154.05-grid-azure.run
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
