# syntax = edrevo/dockerfile-plus

INCLUDE+ base/Dockerfile.common

# NCCL & NCCL tests

ARG NCCL_VERSION=2.26.2-1

ENV NCCL_HOME=/usr/local
ENV CUDA_HOME=/usr/local/cuda
ENV OPEN_MPI_PATH=/usr/lib/x86_64-linux-gnu/openmpi
ENV NCCL_TESTS_HOME=/opt/nccl-tests
ENV PATH="${NCCL_TESTS_HOME}/build:${PATH}"
ENV LD_LIBRARY_PATH="${OPEN_MPI_PATH}/lib:${NCCL_HOME}/lib:${LD_LIBRARY_PATH}"

RUN cuda_version=$(echo ${CUDA_VERSION} | awk -F . '{ print $1"-"$2 }') \
    && apt-get install -y --no-install-recommends \
        cuda-libraries-dev-${cuda_version} \
        cuda-nvcc-${cuda_version} \
        libhwloc-dev \
        autoconf \
        automake \
        libtool \
        libopenmpi-dev

RUN cd $HOME \
    && git clone https://github.com/NVIDIA/nccl.git -b v${NCCL_VERSION} \
    && cd nccl \
    && make -j$(nproc) src.build BUILDDIR=${NCCL_HOME} \
    && git clone https://github.com/NVIDIA/nccl-tests ${NCCL_TESTS_HOME} \
    && cd ${NCCL_TESTS_HOME} \
    && make -j$(nproc) \
        MPI=1 \
        MPI_HOME=${OPEN_MPI_PATH} \
        CUDA_HOME=${CUDA_HOME} \
        NCCL_HOME=${NCCL_HOME} \
    && echo "${NCCL_HOME}/lib" >> /etc/ld.so.conf.d/nccl.conf \
    && ldconfig

ARG FLAVOR
ENV FLAVOR=${FLAVOR}    

# If FLAVOR is base, uninstall development packages to reduce image size
RUN if [ "$FLAVOR" = "base" ]; then \
    cuda_version=$(echo ${CUDA_VERSION} | awk -F . '{ print $1"-"$2 }') \
    && apt-get remove -y \
        cuda-nvcc-${cuda_version} \
        libhwloc-dev \
        autoconf \
        automake \
        libtool \
        libopenmpi-dev \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*; \
fi
