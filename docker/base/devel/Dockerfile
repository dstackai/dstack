# syntax = edrevo/dockerfile-plus

INCLUDE+ base/Dockerfile

# NCCL & NCCL tests

ARG NCCL_VERSION=2.26.2-1

ENV NCCL_HOME=/usr/local
ENV CUDA_PATH=/usr/local/cuda
ENV OPEN_MPI_PATH=/usr/lib/x86_64-linux-gnu/openmpi
ENV NCCL_TESTS_PATH=/opt/nccl-tests
ENV PATH="${LIBFABRIC_PATH}/bin:${OPEN_MPI_PATH}/bin:${NCCL_TESTS_PATH}:${PATH}"
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
    && git clone https://github.com/NVIDIA/nccl-tests ${NCCL_TESTS_PATH} \
    && cd ${NCCL_TESTS_PATH} \
    && make -j$(nproc) \
        MPI=1 \
        MPI_HOME=${OPEN_MPI_PATH} \
        CUDA_HOME=${CUDA_PATH} \
        NCCL_HOME=${NCCL_HOME} \
    && echo "${NCCL_HOME}/lib" >> /etc/ld.so.conf.d/nccl.conf \
    && ldconfig
