#!/bin/bash

set -e

# Common packages across all versions
DEPS="
  net-tools
  ssl-cert
  nvme-cli
  zip
  unzip
  unrar
  htop
  ifstat
  sysstat
  coreutils
  tree
  jq
  gdb
  ufw
  python3-pip
  python3-boto
  python3-boto3
  "

# No `apt-get update` here on purpose: the apt package indexes are already
# refreshed by apt-upgrade.sh, which always runs right before this script.

# Install basic packages
for dep in $DEPS; do
  if ! dpkg -s $dep > /dev/null 2>&1; then
    echo "Attempting installation of missing package: $dep"
    sudo DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=60 install -y -q $dep
  fi
done

# Uninstall amazon-ssm-agent, which comes with Ubuntu AMI via snap.
sudo snap remove amazon-ssm-agent || true

# Uninstall snapd, which is not used by us.
sudo apt-get -o DPkg::Lock::Timeout=60 purge -y snapd

# Uninstall ec2-instance-connect, which is not used by us.
# This resolves ec2-instance-connect.service failure during boot,
# which causes "systemctl status" in "degraded" state.
sudo apt-get -o DPkg::Lock::Timeout=60 purge -y --auto-remove ec2-instance-connect
