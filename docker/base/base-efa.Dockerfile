# syntax = edrevo/dockerfile-plus

# Build stage
FROM nvidia/cuda:12.1.1-base-ubuntu20.04 AS builder

ARG NCCL_VERSION=2.26.2-1
ARG EFA_VERSION=1.38.1
ARG OFI_VERSION=1.14.0

ENV NCCL_HOME=/opt/nccl
ENV OFI_NCCL_HOME=/opt/amazon/ofi-nccl
ENV CUDA_HOME=/usr/local/cuda
ENV LIBFABRIC_PATH=/opt/amazon/efa
ENV OPEN_MPI_PATH=/opt/amazon/openmpi
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

RUN cd /tmp \
    && curl -O https://s3-us-west-2.amazonaws.com/aws-efa-installer/aws-efa-installer-${EFA_VERSION}.tar.gz \
    && tar -xf aws-efa-installer-${EFA_VERSION}.tar.gz \
    && cd aws-efa-installer \
    && ./efa_installer.sh -y --skip-kmod -g

RUN cd /tmp \
    && git clone https://github.com/aws/aws-ofi-nccl.git -b v${OFI_VERSION} \
    && cd aws-ofi-nccl \
    && ./autogen.sh \
    && ./configure \
        --with-cuda=${CUDA_HOME} \
        --with-libfabric=${LIBFABRIC_PATH} \
        --with-mpi=${OPEN_MPI_PATH} \
        --disable-tests \
        --prefix=${NCCL_HOME} \
    && make -j$(nproc) \
    && make install

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
ENV LIBFABRIC_PATH=/opt/amazon/efa
ENV OPEN_MPI_PATH=/opt/amazon/openmpi
ENV NCCL_TESTS_HOME=/opt/nccl-tests
ENV PATH="${LIBFABRIC_PATH}/bin:${OPEN_MPI_PATH}/bin:${PATH}"

COPY --from=builder ${NCCL_HOME} ${NCCL_HOME}
COPY --from=builder ${OFI_NCCL_HOME} ${OFI_NCCL_HOME}
COPY --from=builder /etc/ld.so.conf.d/100_ofinccl.conf /etc/ld.so.conf.d/100_ofinccl.conf
COPY --from=builder ${NCCL_TESTS_HOME}/build ${NCCL_TESTS_HOME}

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libevent-dev \
        libhwloc-dev \
    && cd /tmp \
    && curl -O https://s3-us-west-2.amazonaws.com/aws-efa-installer/aws-efa-installer-${EFA_VERSION}.tar.gz \
    && tar -xf aws-efa-installer-${EFA_VERSION}.tar.gz \
    && cd aws-efa-installer \
    && ./efa_installer.sh -y --skip-kmod -g
    && rm -rf /tmp/aws-efa-installer /var/lib/apt/lists/* \
    && echo "${NCCL_HOME}/lib" >> /etc/ld.so.conf.d/nccl.conf \
    && echo "${OPEN_MPI_PATH}/lib" >> /etc/ld.so.conf.d/openmpi.conf \
    && echo "${LIBFABRIC_PATH}/lib" >> /etc/ld.so.conf.d/efa.conf \
    && ldconfig
