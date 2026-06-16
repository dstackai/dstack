#!/bin/bash

# based on https://learn.microsoft.com/en-us/azure/virtual-machines/extensions/hpccompute-gpu-linux#known-issues
# this is a temporary solution only required until the issue is fixed

set -e

# Install the latest available 6.8 Azure kernel. The exact revision Azure ships
# in the repos changes over time, so we resolve it dynamically instead of pinning
# a specific one (which eventually gets removed and breaks the build).
sudo apt-get update
KERNEL_VERSION=$(apt-cache search --names-only '^linux-image-6\.8\.0-[0-9]+-azure$' | awk '{print $1}' | sed 's/^linux-image-//' | sort -V | tail -1)

if [ -z "$KERNEL_VERSION" ]; then
    echo "No linux-image-6.8.0-*-azure kernel available in the repositories" >&2
    exit 1
fi
echo "Installing Azure kernel $KERNEL_VERSION"
sudo DEBIAN_FRONTEND=noninteractive apt install "linux-image-$KERNEL_VERSION" "linux-headers-$KERNEL_VERSION" -y

# Update the Grub entry name
grub_entry_name="$(sudo grep -Po "menuentry '\KUbuntu, with Linux 6\.8[^(']+" /boot/grub/grub.cfg | sort -V | head -1)"
sudo sed -i "s/^\s*GRUB_DEFAULT=.*$/GRUB_DEFAULT='Advanced options for Ubuntu>$grub_entry_name'/" /etc/default/grub
sudo update-grub

# Disable the kernel package upgrade
sudo apt-mark hold $(dpkg --get-selections | grep -Po "^linux[^\t]+${grub_entry_name##* }")
