#!/bin/bash
set -e
RUNNER_VERSION=${RUNNER_VERSION:-latest}

function install_fuse {
  sudo apt install s3fs -y
  if [ -e "/etc/fuse.conf" ]; then
    echo "THIS /etc/fuse.conf"
    sudo sed "s/# *user_allow_other/user_allow_other/" /etc/fuse.conf > t
    sudo mv t /etc/fuse.conf
  else
    echo "user_allow_other" | tee -a /etc/fuse.conf > /dev/null
  fi
}

function install_stgn {
  sudo curl --output /usr/local/bin/dstack-runner "https://dstack-runner-downloads-stgn.s3.eu-west-1.amazonaws.com/${RUNNER_VERSION}/binaries/dstack-runner-linux-amd64"
  sudo chmod +x /usr/local/bin/dstack-runner
  dstack-runner --version
  install_fuse
}

function install_prod {
  sudo curl --output /usr/local/bin/dstack-runner "https://dstack-runner-downloads.s3.eu-west-1.amazonaws.com/latest/binaries/dstack-runner-linux-amd64"
  sudo chmod +x /usr/local/bin/dstack-runner
  dstack-runner --version
  install_fuse
}

if [[ $DSTACK_STAGE == "PROD" ]]; then
  install_prod
else
  install_stgn
fi