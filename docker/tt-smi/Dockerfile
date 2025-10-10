FROM ubuntu:20.04

ARG IMAGE_NAME
ARG TT_SMI_VERSION
ARG BUILD_DATE

ENV PATH="/root/.cargo/bin:${PATH}"

RUN \
    apt-get update && \
    apt-get install -y curl git python3 python3-pip && \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y && \
    pip3 install --no-cache-dir git+https://github.com/tenstorrent/tt-smi@v${TT_SMI_VERSION} && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["/usr/local/bin/tt-smi"]
CMD ["--help"]

LABEL org.opencontainers.image.title="${IMAGE_NAME}"
LABEL org.opencontainers.image.version="${TT_SMI_VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
