#!/bin/bash
#
# Wait until another process releases an apt/dpkg lock.
#
# This is a hack and it might not work for all cases. A better way of handling
# apt races is the `-o DPkg::Lock::Timeout=X` option, but it does not work for
# `apt-get update`.
#

while sudo fuser /var/{lib/{dpkg,apt/lists},cache/apt/archives}/lock >/dev/null 2>&1; do
   sleep 1
done
