# syntax = edrevo/dockerfile-plus

INCLUDE+ base/Dockerfile

# NCCL & NCCL tests

ARG NCCL_VERSION=2.26.2-1

ENV NCCL_HOME=/usr/local
ENV CUDA_PATH=/usr/local/cuda
ENV OPEN_MPI_PATH=/usr/lib/x86_64-linux-gnu/openmpi
ENV LD_LIBRARY_PATH="${OPEN_MPI_PATH}/lib:${NCCL_HOME}/lib:${LD_LIBRARY_PATH}"
ENV PATH="${OPEN_MPI_PATH}/bin:${HOME}/nccl-tests/build:${PATH}"

RUN apt-get install -y --no-install-recommends \
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
        NCCL_HOME=${NCCL_HOME}
