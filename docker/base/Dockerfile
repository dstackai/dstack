ARG FLAVOR
FROM nvidia/cuda:12.1.1-${FLAVOR}-ubuntu20.04

ARG PYTHON
ARG _UV_HOME="/opt/uv"
ENV UV_PYTHON="${PYTHON}"
ENV UV_INSTALL_DIR="${_UV_HOME}/bin"
ENV UV_PYTHON_INSTALL_DIR="${_UV_HOME}/python"
ENV UV_PYTHON_BIN_DIR="${UV_PYTHON_INSTALL_DIR}/bin"
ENV UV_MANAGED_PYTHON=1
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

ENV PATH="${UV_INSTALL_DIR}:${UV_PYTHON_BIN_DIR}:${PATH}"

RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-key adv --fetch-keys https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2004/x86_64/3bf863cc.pub && \
    apt-get update --fix-missing && \
    apt-get upgrade -y && \
    ln -fs /usr/share/zoneinfo/America/New_York /etc/localtime && \
    apt-get install -y tzdata && \
    dpkg-reconfigure --frontend noninteractive tzdata && \
    apt-get install -y bzip2 ca-certificates curl build-essential git libglib2.0-0 libsm6 libxext6 libxrender1 mercurial openssh-server subversion wget && \
    sed -i "s/.*PasswordAuthentication.*/PasswordAuthentication no/g" /etc/ssh/sshd_config && mkdir /run/sshd && \
    mkdir ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && rm /etc/ssh/ssh_host_*

RUN curl -LsSf https://astral.sh/uv/install.sh | INSTALLER_NO_MODIFY_PATH=1 sh && \
    uv python install --preview --default
