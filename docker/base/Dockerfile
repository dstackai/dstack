# syntax = edrevo/dockerfile-plus

# Build stage
FROM nvidia/cuda:12.1.1-base-ubuntu20.04 AS builder

ARG NCCL_VERSION=2.26.2-1

ENV NCCL_HOME=/opt/nccl
ENV CUDA_HOME=/usr/local/cuda
ENV OPEN_MPI_PATH=/usr/lib/x86_64-linux-gnu/openmpi
ENV NCCL_TESTS_HOME=/opt/nccl-tests

# Install build dependencies
RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-key adv --fetch-keys https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2004/x86_64/3bf863cc.pub \
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

# Build NCCL
RUN cd /tmp \
    && git clone https://github.com/NVIDIA/nccl.git -b v${NCCL_VERSION} \
    && cd nccl \
    && make -j$(nproc) src.build BUILDDIR=${NCCL_HOME}

# Build NCCL tests
RUN git clone https://github.com/NVIDIA/nccl-tests ${NCCL_TESTS_HOME} \
    && cd ${NCCL_TESTS_HOME} \
    && make -j$(nproc) \
        MPI=1 \
        MPI_HOME=${OPEN_MPI_PATH} \
        CUDA_HOME=${CUDA_HOME} \
        NCCL_HOME=${NCCL_HOME}

# Final stage
INCLUDE+ base/Dockerfile.common

ENV NCCL_HOME=/opt/nccl
ENV NCCL_TESTS_HOME=/opt/nccl-tests

COPY --from=builder ${NCCL_HOME}/lib ${NCCL_HOME}/lib
COPY --from=builder ${NCCL_HOME}/include ${NCCL_HOME}/include
COPY --from=builder ${NCCL_TESTS_HOME}/build ${NCCL_TESTS_HOME}/build

ARG FLAVOR

# Configure library paths
RUN apt-get update \
    && apt-get install -y --no-install-recommends openmpi-bin \
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
