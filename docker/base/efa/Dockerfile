# syntax = edrevo/dockerfile-plus

INCLUDE+ base/Dockerfile.common

ENV NCCL_HOME=/usr/local
ENV CUDA_HOME=/usr/local/cuda
ENV LIBFABRIC_PATH=/opt/amazon/efa
ENV MPI_HOME=/opt/amazon/openmpi
ENV NCCL_TESTS_HOME=/opt/nccl-tests
ENV PATH="${LIBFABRIC_PATH}/bin:${MPI_HOME}/bin:${NCCL_TESTS_HOME}/build:${PATH}"
ENV LD_LIBRARY_PATH="${MPI_HOME}/lib:${NCCL_HOME}/lib:${LD_LIBRARY_PATH}"

ARG EFA_VERSION=1.38.1
ARG NCCL_VERSION=2.26.2-1
ARG OFI_VERSION=1.14.0
ARG FLAVOR

RUN cuda_version=$(echo ${CUDA_VERSION} | awk -F . '{ print $1"-"$2 }') \
    && apt-get install -y --no-install-recommends \
        cuda-libraries-dev-${cuda_version} \
        cuda-nvcc-${cuda_version} \
        libhwloc-dev \
        autoconf \
        automake \
        libtool \
    && cd $HOME \
    && curl -O https://s3-us-west-2.amazonaws.com/aws-efa-installer/aws-efa-installer-${EFA_VERSION}.tar.gz \
    && tar -xf aws-efa-installer-${EFA_VERSION}.tar.gz \
    && cd aws-efa-installer \
    && ./efa_installer.sh -y --skip-kmod -g \
    && cd $HOME \
    && git clone https://github.com/NVIDIA/nccl.git -b v${NCCL_VERSION} \
    && cd nccl \
    && make -j$(nproc) src.build BUILDDIR=${NCCL_HOME} \
    && cd $HOME \
    && git clone https://github.com/aws/aws-ofi-nccl.git -b v${OFI_VERSION} \
    && cd aws-ofi-nccl \
    && ./autogen.sh \
    && ./configure \
        --with-cuda=${CUDA_HOME} \
        --with-libfabric=${LIBFABRIC_PATH} \
        --with-mpi=${MPI_HOME} \
        --with-nccl=${NCCL_HOME} \
        --disable-tests \
        --prefix=${NCCL_HOME} \
    && make -j$(numproc) \
    && make install \
    && git clone https://github.com/NVIDIA/nccl-tests ${NCCL_TESTS_HOME} \
    && cd ${NCCL_TESTS_HOME} \
    && make -j$(numproc) \
        MPI=1 \
        MPI_HOME=${MPI_HOME} \
        CUDA_HOME=${CUDA_HOME} \
        NCCL_HOME=${NCCL_HOME} \
    && echo "${NCCL_HOME}/lib" >> /etc/ld.so.conf.d/nccl.conf \
    && ldconfig \
    && if [ "$FLAVOR" = "base" ]; then \
        apt-get remove -y \
            cuda-nvcc-${cuda_version} \
            libhwloc-dev \
            autoconf \
            automake \
            libtool \
        && apt-get autoremove -y \
        && apt-get clean \
        && rm -rf /var/lib/apt/lists/*; \
    fi
