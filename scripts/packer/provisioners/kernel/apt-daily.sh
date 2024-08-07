#!/bin/bash

set -e

# conf_path=/etc/systemd/system/apt-daily.timer.d
# conf_file=$conf_path/boot.conf

# sudo mkdir -p "$conf_path"
# echo "[Timer]" | sudo tee "$conf_file"
# echo "Persistent=false" | sudo tee "$conf_file" -a
# echo "OnBootSec=1h" | sudo tee "$conf_file" -a

readonly APT_PERIODIC_CONF_PATH=/etc/apt/apt.conf.d
readonly APT_PERIODIC_CONF_FILE=${APT_PERIODIC_CONF_PATH}/99-kingsoftgames-disable-periodic

# Disable apt-daily and apt-daily-upgrade service
sudo systemctl disable apt-daily.timer
sudo systemctl disable apt-daily-upgrade.timer

# Disable the update/upgrade script
sudo mkdir -p "$APT_PERIODIC_CONF_PATH"
echo 'APT::Periodic::Enable "0";' | sudo tee "$APT_PERIODIC_CONF_FILE"
