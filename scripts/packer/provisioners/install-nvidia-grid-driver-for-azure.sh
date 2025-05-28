#!/bin/bash

# based on https://learn.microsoft.com/en-us/azure/virtual-machines/linux/n-series-driver-setup#install-grid-drivers-on-nv-or-nvv3-series-vms

set -e

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install build-essential linux-azure -y

wget --no-verbose -O NVIDIA-Linux-x86_64-grid.run \
    https://download.microsoft.com/download/c5319e92-672e-4067-8d85-ab66a7a64db3/NVIDIA-Linux-x86_64-550.144.06-grid-azure.run
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
