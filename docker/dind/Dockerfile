# Keep BASE_VERSION (base image tag) and BASE_SHA256 in sync
ARG BASE_VERSION=24.04-20240827003913
ARG BASE_SHA256=c9812aad4dbb79d800e5aecdfe41b66ffe47b73f0c070b5143c5acdcd6643ba1

FROM ghcr.io/ehfd/nvidia-dind@sha256:${BASE_SHA256}

ARG IMAGE_NAME
ARG BASE_VERSION
ARG DSTACK_REVISION
ARG BUILD_DATE

COPY start-dockerd /usr/local/bin/

RUN \
    chmod 755 /usr/local/bin/start-dockerd && \
    rm /usr/local/bin/entrypoint.sh && \
    sed -i -e '/nodaemon/d' -e '/program:entrypoint/,/^[[:space:]]*$/d' /etc/supervisord.conf

ENTRYPOINT []
CMD ["/usr/local/bin/start-dockerd", "-v", "-l"]

LABEL org.opencontainers.image.title="${IMAGE_NAME}"
LABEL org.opencontainers.image.version="${BASE_VERSION}-${DSTACK_REVISION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
