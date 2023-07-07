#!/bin/bash
set -e
RUNNER_VERSION=${RUNNER_VERSION:-latest}

function install_nvidia_docker_runtime {
  sudo apt-get update
  sudo apt-get install -y --no-install-recommends nvidia-docker2
  sudo pkill -SIGHUP dockerd
}

function install_stgn {
  sudo curl --output /usr/local/bin/dstack-runner "https://dstack-runner-downloads-stgn.s3.eu-west-1.amazonaws.com/${RUNNER_VERSION}/binaries/dstack-runner-linux-amd64"
  sudo chmod +x /usr/local/bin/dstack-runner
  dstack-runner --version
}

function install_prod {
  sudo curl --output /usr/local/bin/dstack-runner "https://dstack-runner-downloads.s3.eu-west-1.amazonaws.com/${RUNNER_VERSION}/binaries/dstack-runner-linux-amd64"
  sudo chmod +x /usr/local/bin/dstack-runner
  dstack-runner --version
}

install_nvidia_docker_runtime

if [[ $ENVIRONMENT == "prod" ]]; then
  install_prod
else
  install_stgn
fi
