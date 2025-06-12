ARG FLAVOR
FROM nvidia/cuda:12.1.1-${FLAVOR}-ubuntu20.04

# UV & Python

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
    apt-get install -y bzip2 ca-certificates curl build-essential git libglib2.0-0 libsm6 libxext6 libxrender1 mercurial openssh-server subversion wget \
    libibverbs1 ibverbs-providers ibverbs-utils libibverbs-dev infiniband-diags && \
    sed -i "s/.*PasswordAuthentication.*/PasswordAuthentication no/g" /etc/ssh/sshd_config && mkdir /run/sshd && \
    mkdir ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && rm /etc/ssh/ssh_host_*

RUN curl -LsSf https://astral.sh/uv/install.sh | INSTALLER_NO_MODIFY_PATH=1 sh && \
    uv python install --preview --default

# NCCL & NCCL tests

ARG NCCL_VERSION=2.26.2-1
ARG FLAVOR

ENV FLAVOR=${FLAVOR}
ENV NCCL_HOME=/usr/local
ENV CUDA_PATH=/usr/local/cuda
ENV OPEN_MPI_PATH=/usr/lib/x86_64-linux-gnu/openmpi
ENV LD_LIBRARY_PATH="${OPEN_MPI_PATH}/lib:${NCCL_HOME}/lib:${LD_LIBRARY_PATH}"
ENV PATH="${OPEN_MPI_PATH}/bin:${HOME}/nccl-tests/build:${PATH}"

RUN if [ "${FLAVOR}" = "devel" ]; then \
    apt-get install -y --no-install-recommends \
        libopenmpi-dev \
    && cd $HOME \
    && git clone https://github.com/NVIDIA/nccl.git -b v${NCCL_VERSION} \
    && cd nccl \
    && make -j$(nproc) src.build BUILDDIR=${NCCL_HOME} \
    && cd $HOME \
    && git clone https://github.com/NVIDIA/nccl-tests \
    && cd nccl-tests \
    && make -j$(nproc) \
        MPI=1 \
        MPI_HOME=${OPEN_MPI_PATH} \
        CUDA_HOME=${CUDA_PATH} \
        NCCL_HOME=${NCCL_HOME}; \
    fi
