#!/bin/bash
#
# Upgrade apt packages to latest versions.
#

set -e

sudo apt-get update

# https://devops.stackexchange.com/questions/1139/how-to-avoid-interactive-dialogs-when-running-apt-get-upgrade-y-in-ubuntu-16
sudo DEBIAN_FRONTEND=noninteractive apt-get dist-upgrade -y -q
