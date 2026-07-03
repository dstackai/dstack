ARG UBUNTU_VERSION

# ============================================================================
# common: shared base for all flavors. Select a flavor with `--target <flavor>`
# (base / devel / devel-efa).
# ============================================================================

FROM nvidia/cuda:13.0.3-base-ubuntu${UBUNTU_VERSION}.04 AS common

# ARGs before FROM must be redeclared to be used after FROM
ARG UBUNTU_VERSION

ARG _UV_HOME="/opt/uv"

ENV UV_INSTALL_DIR="${_UV_HOME}/bin"
ENV UV_MANAGED_PYTHON=1
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

ENV PATH="${UV_INSTALL_DIR}:${PATH}"

ENV OMPI_MCA_pml=^cm,ucx
ENV OMPI_MCA_btl=tcp,self
ENV OMPI_MCA_btl_tcp_if_exclude=lo,docker0
ENV NCCL_SOCKET_IFNAME=^docker,lo

RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-get update --fix-missing \
    && apt-get upgrade -y \
    && ln -fs /usr/share/zoneinfo/America/New_York /etc/localtime \
    && apt-get install -y tzdata \
    && dpkg-reconfigure --frontend noninteractive tzdata \
    && apt-get install -y bzip2 ca-certificates curl build-essential git libglib2.0-0 libsm6 libxext6 libxrender1 openssh-server wget \
        libibverbs1 ibverbs-providers ibverbs-utils libibverbs-dev infiniband-diags \
    # nvidia/cuda ships nvidia's apt singing key in legacy format (/etc/apt/trusted.gpg).
    # This lead to warnings, so we install cuda-keyring.
    && wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu${UBUNTU_VERSION}04/x86_64/cuda-keyring_1.1-1_all.deb \
    && dpkg -i cuda-keyring_1.1-1_all.deb \
    && rm cuda-keyring_1.1-1_all.deb \
    && rm -f /etc/apt/sources.list.d/cuda.list \
    && sed -i "s/.*PasswordAuthentication.*/PasswordAuthentication no/g" /etc/ssh/sshd_config \
    && mkdir /run/sshd \
    && mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys \
    && chmod 600 ~/.ssh/authorized_keys \
    && rm /etc/ssh/ssh_host_* \
    # User: UID/GID 1001 because Ubuntu 24.04 ships a default 'ubuntu' user at 1000.
    && apt-get install -y sudo \
    && groupadd -g 1001 dstack \
    && useradd -u 1001 -g 1001 -G sudo -s /bin/bash -m dstack \
    && echo 'dstack ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/dstack \
    # Default working dir
    && mkdir -p /dstack/run \
    && chmod a+rwx /dstack/run \
    # Cleanup
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | INSTALLER_NO_MODIFY_PATH=1 sh \
    && uv python install --preview --default

# ============================================================================
# builder: builds NCCL and nccl-tests from source for the base/devel flavors.
# ============================================================================

FROM nvidia/cuda:13.0.3-base-ubuntu${UBUNTU_VERSION}.04 AS builder

ENV NCCL_HOME=/opt/nccl
ENV CUDA_HOME=/usr/local/cuda
ENV OPEN_MPI_PATH=/usr/lib/x86_64-linux-gnu/openmpi

RUN export DEBIAN_FRONTEND=noninteractive \
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

ARG NCCL_VERSION=2.30.7-1

RUN cd /tmp \
    && git clone https://github.com/NVIDIA/nccl.git -b v${NCCL_VERSION} \
    && cd nccl \
    && make -j$(nproc) src.build BUILDDIR=${NCCL_HOME}

RUN cd /opt \
    && git clone https://github.com/NVIDIA/nccl-tests \
    && cd nccl-tests \
    && make -j$(nproc) \
        MPI=1 \
        MPI_HOME=${OPEN_MPI_PATH} \
        CUDA_HOME=${CUDA_HOME} \
        NCCL_HOME=${NCCL_HOME}

# ============================================================================
# base: common + NCCL (from builder) + OpenMPI.
# ============================================================================

FROM common AS base

ENV NCCL_HOME=/opt/nccl

COPY --from=builder ${NCCL_HOME} ${NCCL_HOME}
COPY --from=builder /opt/nccl-tests/build /opt/nccl-tests/build

RUN apt-get update \
    && apt-get install -y --no-install-recommends openmpi-bin \
    && rm -rf /var/lib/apt/lists/* \
    && echo "${NCCL_HOME}/lib" >> /etc/ld.so.conf.d/nccl.conf \
    && ldconfig

WORKDIR /dstack/run

# ============================================================================
# devel: base + CUDA development libraries and NVCC.
# ============================================================================

FROM base AS devel

RUN cuda_version=$(echo ${CUDA_VERSION} | awk -F . '{ print $1"-"$2 }') \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        cuda-libraries-dev-${cuda_version} \
        cuda-nvcc-${cuda_version} \
        libhwloc-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /dstack/run

# ============================================================================
# devel-efa: common + CUDA dev libraries + AWS EFA + EFA-aware NCCL.
# ============================================================================

FROM common AS devel-efa

ENV NCCL_HOME=/usr/local
ENV CUDA_HOME=/usr/local/cuda
ENV LIBFABRIC_PATH=/opt/amazon/efa
ENV OPEN_MPI_PATH=/opt/amazon/openmpi
ENV PATH="${LIBFABRIC_PATH}/bin:${OPEN_MPI_PATH}/bin:${PATH}"
ENV LD_LIBRARY_PATH="${OPEN_MPI_PATH}/lib:${LD_LIBRARY_PATH}"

RUN cuda_version=$(echo ${CUDA_VERSION} | awk -F . '{ print $1"-"$2 }') \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        cuda-libraries-dev-${cuda_version} \
        cuda-nvcc-${cuda_version} \
    && rm -rf /var/lib/apt/lists/*

ARG EFA_VERSION=1.48.0

RUN cd /tmp \
    && apt-get update \
    && curl -O https://s3-us-west-2.amazonaws.com/aws-efa-installer/aws-efa-installer-${EFA_VERSION}.tar.gz \
    && tar -xf aws-efa-installer-${EFA_VERSION}.tar.gz \
    && cd aws-efa-installer \
    && ./efa_installer.sh -y --skip-kmod -g \
    && rm -rf /tmp/aws-efa-installer /var/lib/apt/lists/*

ARG NCCL_VERSION=2.30.7-1

RUN cd /tmp \
    && git clone https://github.com/NVIDIA/nccl.git -b v${NCCL_VERSION} \
    && cd nccl \
    && make -j$(nproc) src.build BUILDDIR=${NCCL_HOME} \
    && rm -rf /tmp/nccl

RUN cd /opt \
    && git clone https://github.com/NVIDIA/nccl-tests \
    && cd nccl-tests \
    && make -j$(nproc) \
        MPI=1 \
        MPI_HOME=${OPEN_MPI_PATH} \
        CUDA_HOME=${CUDA_HOME} \
        NCCL_HOME=${NCCL_HOME}

WORKDIR /dstack/run
