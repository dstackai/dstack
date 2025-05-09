ARG UBUNTU_VERSION

FROM ubuntu:${UBUNTU_VERSION}

ARG IMAGE_NAME
ARG UBUNTU_VERSION
ARG ROCM_VERSION
ARG DSTACK_REVISION
ARG BUILD_DATE

ENV PATH="/opt/rocm/bin:${PATH}"

RUN \
    export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && \
    apt-get install -y --no-install-recommends wget ca-certificates && \
    base_url="https://repo.radeon.com/amdgpu-install/${ROCM_VERSION}/ubuntu/${UBUNTU_VERSION}/" && \
    deb_name=$(wget -qO- "${base_url}" | grep -Po '(?<=href=")amdgpu-install_[^"]+') && \
    wget -O amdgpu-install.deb "${base_url}${deb_name}" && \
    apt-get install -y --no-install-recommends ./amdgpu-install.deb && \
    rm ./amdgpu-install.deb && \
    apt-get update && \
    apt-get install -y amd-smi-lib

ENTRYPOINT ["/opt/rocm/bin/amd-smi"]
CMD ["--help"]

LABEL org.opencontainers.image.title="${IMAGE_NAME}"
LABEL org.opencontainers.image.version="${ROCM_VERSION}-${DSTACK_REVISION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
