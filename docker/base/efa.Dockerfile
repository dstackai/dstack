# syntax = edrevo/dockerfile-plus

INCLUDE+ base/Dockerfile.common

ENV NCCL_HOME=/usr/local
ENV CUDA_HOME=/usr/local/cuda
ENV LIBFABRIC_PATH=/opt/amazon/efa
ENV OPEN_MPI_PATH=/opt/amazon/openmpi
ENV PATH="${LIBFABRIC_PATH}/bin:${OPEN_MPI_PATH}/bin:${PATH}"
ENV LD_LIBRARY_PATH="${OPEN_MPI_PATH}/lib:${LD_LIBRARY_PATH}"

# Prerequisites

RUN cuda_version=$(echo ${CUDA_VERSION} | awk -F . '{ print $1"-"$2 }') \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        cuda-libraries-dev-${cuda_version} \
        cuda-nvcc-${cuda_version} \
        libhwloc-dev \
        autoconf \
        automake \
        libtool \
    && rm -rf /var/lib/apt/lists/*

# EFA

ARG EFA_VERSION=1.38.1

RUN cd /tmp \
    && apt-get update \
    && curl -O https://s3-us-west-2.amazonaws.com/aws-efa-installer/aws-efa-installer-${EFA_VERSION}.tar.gz \
    && tar -xf aws-efa-installer-${EFA_VERSION}.tar.gz \
    && cd aws-efa-installer \
    && ./efa_installer.sh -y --skip-kmod -g \
    && rm -rf /tmp/aws-efa-installer /var/lib/apt/lists/*

# NCCL

ARG NCCL_VERSION=2.26.2-1

RUN cd /tmp \
    && git clone https://github.com/NVIDIA/nccl.git -b v${NCCL_VERSION} \
    && cd nccl \
    && make -j$(nproc) src.build BUILDDIR=${NCCL_HOME} \
    && rm -rf /tmp/nccl

# AWS OFI NCCL

ARG OFI_VERSION=1.14.0

RUN cd /tmp \
    && git clone https://github.com/aws/aws-ofi-nccl.git -b v${OFI_VERSION} \
    && cd aws-ofi-nccl \
    && ./autogen.sh \
    && ./configure \
        --with-cuda=${CUDA_HOME} \
        --with-libfabric=${LIBFABRIC_PATH} \
        --with-mpi=${OPEN_MPI_PATH} \
        --with-cuda=${CUDA_HOME} \
        --with-nccl=${NCCL_HOME} \
        --disable-tests \
        --prefix=${NCCL_HOME} \
    && make -j$(nproc) \
    && make install \
    && rm -rf /tmp/aws-ofi-nccl /var/lib/apt/lists/*

# NCCL Tests

RUN cd /opt \
    && git clone https://github.com/NVIDIA/nccl-tests \
    && cd nccl-tests \
    && make -j$(nproc) \
        MPI=1 \
        MPI_HOME=${OPEN_MPI_PATH} \
        CUDA_HOME=${CUDA_HOME} \
        NCCL_HOME=${NCCL_HOME}
