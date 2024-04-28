#!/bin/bash

# Instructions from
# https://docs.docker.com/engine/install/ubuntu/

set -e

# =============================================================================

readonly SCRIPT_INSTALL_DIR="/opt/docker/bin"

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_NAME="$(basename "$0")"

# =============================================================================

function print_usage {
  echo
  echo "Usage: install-docker [OPTIONS]"
  echo
  echo "This script can be used to install Docker CE on AWS EC2."
  echo
  echo "Options:"
  echo
  echo -e "  --version\tThe version of Docker to install."
  echo
  echo "Example:"
  echo
  echo "  install-docker --version 18.09.7"
}

function log {
  local readonly level="$1"
  local readonly message="$2"
  local readonly timestamp=$(date +"%Y-%m-%d %H:%M:%S")
  >&2 echo -e "${timestamp} [${level}] [$SCRIPT_NAME] ${message}"
}

function log_info {
  local readonly message="$1"
  log "INFO" "$message"
}

function log_error {
  local readonly message="$1"
  log "ERROR" "$message"
}

function assert_not_empty {
  local readonly arg_name="$1"
  local readonly arg_value="$2"

  if [[ -z "$arg_value" ]]; then
    log_error "The value for '$arg_name' cannot be empty"
    print_usage
    exit 1
  fi
}

# =============================================================================

function install_docker_ce {
  local readonly version="$1"
  local readonly arch=$(dpkg --print-architecture)
  local readonly codename=$(lsb_release -cs)

  # Use aliyun's mirror of Docker CE, if in AWS China regions.
  # https://developer.aliyun.com/mirror/docker-ce
  local readonly az=$(ec2metadata --availability-zone)
  local repo_url="https://download.docker.com/linux/ubuntu"
  if [[ $az == cn-* ]]; then
    repo_url="https://mirrors.aliyun.com/docker-ce/linux/ubuntu"
  fi

  log_info "Add Docker's official GPG Key"
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

  log_info "Add Docker's apt repository (stable)"
  echo "deb [arch=${arch} signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] ${repo_url} ${codename} stable" | sudo tee /etc/apt/sources.list.d/docker.list

  log_info 'apt-get update'
  sudo apt-get update

  readonly docker_version=$(apt-cache madison docker-ce | grep $version | head -1 | awk '{print $3}')
  log_info "Installing docker-ce=$docker_version"
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -q docker-ce=$docker_version docker-ce-cli=$docker_version containerd.io docker-compose-plugin acl
}

function hold_docker_pkgs {
  log_info 'Pin docker-ce to current version'
  sudo apt-mark hold docker-ce docker-ce-cli containerd.io docker-compose-plugin
}

function setup_docker_group {
  log_info 'Add current user to docker group'
  sudo gpasswd -a $USER docker
}

function stop_and_disable_docker_service {
  log_info 'Stop and disable docker.service and containerd.service'
  sudo systemctl stop docker.service
  sudo systemctl disable docker.service
  sudo systemctl stop containerd.service
  sudo systemctl disable containerd.service
}

function purge_docker_data_dir {
  log_info 'Removing data under /var/lib/docker'
  sudo rm -rf /var/lib/docker
}

function copy_docker_run_script {
  log_info "Copying Docker run script to $SCRIPT_INSTALL_DIR"
  sudo mkdir -p "$SCRIPT_INSTALL_DIR"
  sudo cp -vf "$SCRIPT_DIR/run-docker" "$SCRIPT_INSTALL_DIR"
}

function permision_ubuntu {
  log_info "Set permision docker.sock"
  sudo setfacl --modify user:$USER:rw /var/run/docker.sock
}

# =============================================================================

function install {
  local version=""

  while [[ $# > 0 ]]; do
    local key="$1"

    case "$key" in
      --version)
        version="$2"
        shift
        ;;
      --help)
        print_usage
        exit
        ;;
      *)
        log_error "Unrecognized argument: $key"
        print_usage
        exit 1
        ;;
    esac

    shift
  done

  assert_not_empty "--version" "$version"

  log_info "Start installing docker $version"

  install_docker_ce "$version"
  hold_docker_pkgs
  setup_docker_group
  stop_and_disable_docker_service
  purge_docker_data_dir
  copy_docker_run_script
  permision_ubuntu
  
  log_info "Docker $version install complete!"
}

install "$@"
