#!/bin/bash

# based on https://learn.microsoft.com/en-us/azure/virtual-machines/extensions/hpccompute-gpu-linux#known-issues
# this is a temporary solution only required until the issue is fixed

set -e

# Install 6.8 kernel
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt install linux-image-6.8.0-1015-azure linux-headers-6.8.0-1015-azure -y

# Update the Grub entry name
grub_entry_name="$(sudo grep -Po "menuentry '\KUbuntu, with Linux 6\.8[^(']+" /boot/grub/grub.cfg | sort -V | head -1)"
sudo sed -i "s/^\s*GRUB_DEFAULT=.*$/GRUB_DEFAULT='Advanced options for Ubuntu>$grub_entry_name'/" /etc/default/grub
sudo update-grub

# Disable the kernel package upgrade
sudo apt-mark hold $(dpkg --get-selections | grep -Po "^linux[^\t]+${grub_entry_name##* }")
