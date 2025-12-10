#!/bin/bash
#
# Upgrade apt packages to latest versions.
#

set -e

#
# Run apt-get update, but retry in case the lock is held by another process.
#
# A better way of handling apt races is the `-o DPkg::Lock::Timeout=X` option,
# but it does not work with `apt-get update`.
#
# This function was added specifically for the `oci` backend, where our build
# process conflicts with OCI's instance agent.
#
apt_update_with_retry() {
    local MAX_RETRIES=10
    local RETRY_DELAY=3
    local COUNT=0
    local LOGFILE=$(mktemp)

    while [ $COUNT -lt $MAX_RETRIES ]; do
        set +e
        sudo apt-get update 2>&1 | tee "$LOGFILE"
        local EXIT_CODE=${PIPESTATUS[0]}
        set -e

        if grep -q "Could not get lock" "$LOGFILE"; then
            echo "apt lock file is held by another process. Retrying in $RETRY_DELAY seconds..."
            COUNT=$((COUNT + 1))
            sleep $RETRY_DELAY
        else
            return $EXIT_CODE
        fi
    done

    echo "apt-get update failed due to lock being held after $MAX_RETRIES attempts."
    return 1
}

apt_update_with_retry
# See https://man7.org/linux/man-pages/man1/dpkg.1.html#OPTIONS for confold/confdef
sudo DEBIAN_FRONTEND=noninteractive apt-get \
    -o DPkg::Lock::Timeout=60 \
    -o Dpkg::Options::=--force-confold \
    -o Dpkg::Options::=--force-confdef \
    dist-upgrade -y -q
