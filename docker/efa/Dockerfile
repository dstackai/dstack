ARG BASE_IMAGE=dstackai/base:py3.12-0.7-cuda-12.1

FROM ${BASE_IMAGE}

ENV PREFIX=/usr/local
ENV CUDA_PATH=/usr/local/cuda
ENV LIBFABRIC_PATH=/opt/amazon/efa
ENV OPEN_MPI_PATH=/opt/amazon/openmpi
ENV PATH="${LIBFABRIC_PATH}/bin:${OPEN_MPI_PATH}/bin:${PATH}"
ENV LD_LIBRARY_PATH="${OPEN_MPI_PATH}/lib:${LD_LIBRARY_PATH}"

# prerequisites

RUN cuda_version=$(echo ${CUDA_VERSION} | awk -F . '{ print $1"-"$2 }') \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        cuda-libraries-dev-${cuda_version} \
        cuda-nvcc-${cuda_version} \
        libhwloc-dev \
        autoconf \
        automake \
        libtool

# EFA

ARG EFA_VERSION=1.38.1

RUN cd $HOME \
    && curl -O https://s3-us-west-2.amazonaws.com/aws-efa-installer/aws-efa-installer-${EFA_VERSION}.tar.gz \
    && tar -xf aws-efa-installer-${EFA_VERSION}.tar.gz \
    && cd aws-efa-installer \
    && ./efa_installer.sh -y --skip-kmod -g

# NCCL

ARG NCCL_VERSION=2.26.2-1

RUN cd $HOME \
    && git clone https://github.com/NVIDIA/nccl.git -b v${NCCL_VERSION} \
    && cd nccl \
    && make -j$(nproc) src.build BUILDDIR=${PREFIX}

# AWS OFI NCCL

ARG OFI_VERSION=1.14.0

RUN cd $HOME \
    && git clone https://github.com/aws/aws-ofi-nccl.git -b v${OFI_VERSION} \
    && cd aws-ofi-nccl \
    && ./autogen.sh \
    && ./configure \
        --with-cuda=${CUDA_PATH} \
        --with-libfabric=${LIBFABRIC_PATH} \
        --with-mpi=${OPEN_MPI_PATH} \
        --with-cuda=${CUDA_PATH} \
        --with-nccl=${PREFIX} \
        --disable-tests \
        --prefix=${PREFIX} \
    && make -j$(numproc) \
    && make install

# NCCL Tests

RUN cd $HOME \
    && git clone https://github.com/NVIDIA/nccl-tests \
    && cd nccl-tests \
    && make -j$(numproc) \
        MPI=1 \
        MPI_HOME=${OPEN_MPI_PATH} \
        CUDA_HOME=${CUDA_PATH} \
        NCCL_HOME=${PREFIX}

ARG BUILD_DATE
ARG IMAGE_NAME
ARG DSTACK_REVISION

LABEL org.opencontainers.image.title="${IMAGE_NAME}"
LABEL org.opencontainers.image.version="${EFA_VERSION}-${DSTACK_REVISION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
