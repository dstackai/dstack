# syntax = edrevo/dockerfile-plus
ARG UBUNTU_VERSION

# Build stage
FROM nvidia/cuda:12.1.1-base-ubuntu${UBUNTU_VERSION}.04 AS builder

ENV NCCL_HOME=/opt/nccl
ENV CUDA_HOME=/usr/local/cuda
ENV OPEN_MPI_PATH=/usr/lib/x86_64-linux-gnu/openmpi

# Prerequisites

RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-key adv --fetch-keys https://developer.download.nvidia.com/compute/cuda/repos/ubuntu${UBUNTU_VERSION}04/x86_64/3bf863cc.pub \
    && apt-get update --fix-missing \
    && apt-get upgrade -y \
    && ln -fs /usr/share/zoneinfo/America/New_York /etc/localtime \
    && apt-get install -y tzdata \
    && dpkg-reconfigure --frontend noninteractive tzdata \
    && cuda_version=$(echo ${CUDA_VERSION} | awk -F . '{ print $1"-"$2 }') \
    && apt-get install -y --no-install-recommends \
        cuda-libraries-dev-${cuda_version} \
        cuda-nvcc-${cuda_version} \
        libhwloc-dev \
        autoconf \
        automake \
        libtool \
        libopenmpi-dev \
        git \
        curl \
        python3 \
        build-essential

# NCCL

ARG NCCL_VERSION=2.26.2-1

RUN cd /tmp \
    && git clone https://github.com/NVIDIA/nccl.git -b v${NCCL_VERSION} \
    && cd nccl \
    && make -j$(nproc) src.build BUILDDIR=${NCCL_HOME}

# NCCL tests

RUN cd /opt \
    && git clone https://github.com/NVIDIA/nccl-tests \
    && cd nccl-tests \
    && make -j$(nproc) \
        MPI=1 \
        MPI_HOME=${OPEN_MPI_PATH} \
        CUDA_HOME=${CUDA_HOME} \
        NCCL_HOME=${NCCL_HOME}

# Final stage

INCLUDE+ base/Dockerfile.common

ENV NCCL_HOME=/opt/nccl

COPY --from=builder ${NCCL_HOME} ${NCCL_HOME}
COPY --from=builder /opt/nccl-tests/build /opt/nccl-tests/build

ARG FLAVOR

# MPI, NVCC, and /etc/ld.so.conf.d

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        openmpi-bin \
    && if [ "$FLAVOR" = "devel" ]; then \
        cuda_version=$(echo ${CUDA_VERSION} | awk -F . '{ print $1"-"$2 }') \
        && apt-get install -y --no-install-recommends \
            cuda-libraries-dev-${cuda_version} \
            cuda-nvcc-${cuda_version} \
            libhwloc-dev; \
    fi \
    && rm -rf /var/lib/apt/lists/* \
    && echo "${NCCL_HOME}/lib" >> /etc/ld.so.conf.d/nccl.conf \
    && ldconfig
