# Define and use build arguments for base image and SHA
ARG BASE_VERSION=24.04-20240827003913
ARG BASE_SHA256=c9812aad4dbb79d800e5aecdfe41b66ffe47b73f0c070b5143c5acdcd6643ba1

# Use NVIDIA's Docker-in-Docker image with a specific SHA256 checksum
FROM ghcr.io/ehfd/nvidia-dind@sha256:${BASE_SHA256}

# Define additional build arguments for image metadata
ARG IMAGE_NAME
ARG BASE_VERSION
ARG DSTACK_REVISION
ARG BUILD_DATE

# Copy custom dockerd start script and set permissions
COPY start-dockerd /usr/local/bin/
RUN chmod 755 /usr/local/bin/start-dockerd && \
    # Remove default entrypoint script and update supervisor config
    rm /usr/local/bin/entrypoint.sh && \
    sed -i -e '/nodaemon/d' \
           -e '/program:entrypoint/,/^[[:space:]]*$/d' /etc/supervisord.conf

# Define empty entrypoint to override base entrypoint
ENTRYPOINT []

# Define CMD to start dockerd in background and log output
CMD ["sh", "-c", "/usr/local/bin/start-dockerd && tail -f /tmp/dockerd.log"]

# Add image metadata labels
LABEL org.opencontainers.image.title="${IMAGE_NAME}" \
      org.opencontainers.image.version="${BASE_VERSION}-${DSTACK_REVISION}" \
      org.opencontainers.image.created="${BUILD_DATE}"
