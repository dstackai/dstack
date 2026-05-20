#!/bin/sh
set -eu

if [ ${#} -lt 2 ]; then
    echo "usage: $(basename "${0}") PATH1 PATH2 [PATH3 ...]" >&2
    exit 1
fi

# Windows is not supported; on Windows a path separator is ';', not ':'
KUBECONFIG=$(IFS=':'; echo "${*}")
export KUBECONFIG
kubectl config view --raw --flatten | grep -Ev '^current-context: '
