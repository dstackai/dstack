#!/bin/bash

set -e

readonly SYSCTL_CONF="/etc/sysctl.d/dstack-kernel-tuning.conf"

sudo tee "$SYSCTL_CONF" <<EOF
# Disable virtual memory
vm.swappiness = 0
# Networking
# upper limit allowed for a listen() backlog
net.core.somaxconn = 1024
# per-socket receive/send buffers
net.core.rmem_max = 16777216
net.core.wmem_max = 16777216
# port range used by TCP and UDP to choose the local port
# note: Nomad allocate ports between 20000 and 32000
# https://www.nomadproject.io/docs/install/production/requirements#ports-used
net.ipv4.ip_local_port_range = 3500 4000
EOF

sudo sysctl -p "$SYSCTL_CONF"
