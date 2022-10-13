#!/bin/bash

#
# Install kernel related packages.
#

set -e

readonly RELEASE=$(lsb_release -rs)

readonly LTS_KERNEL_PKGS="linux-aws-lts-$RELEASE linux-tools-aws-lts-$RELEASE"
readonly ROLLING_KERNEL_PKGS="linux-aws linux-headers-aws linux-image-aws linux-tools-aws"

# Since 2020-04-16, Ubuntu moved to a rolling kernel model on AWS.
# https://ubuntu.com/blog/introducing-the-ubuntu-aws-rolling-kernel-2
#
# We do not want the kernel to roll,
# instead, we want to stay on LTS kernel version to keep things stable and predictable.
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q $LTS_KERNEL_PKGS
sudo apt-get purge -y --auto-remove $ROLLING_KERNEL_PKGS
