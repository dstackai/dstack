#!/bin/bash
#
# Upgrade apt packages to latest versions.
#

set -e

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=60 dist-upgrade -y -q
