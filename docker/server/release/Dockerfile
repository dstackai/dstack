FROM python:3.11-slim

ARG VERSION
ENV VERSION=$VERSION
ENV PYTHONUNBUFFERED=1
ENV DSTACK_SERVER_LOG_FORMAT=json

WORKDIR /dstack-server

RUN apt-get update && apt-get install -y \
    curl \
    git \
    sqlite3 \
    tini \
    && rm -rf /var/lib/apt/lists/*

RUN if [ $(uname -m) = "aarch64" ]; then ARCH="arm64"; else ARCH="x86_64"; fi && \
    curl https://github.com/benbjohnson/litestream/releases/download/v0.5.0/litestream-0.5.0-linux-$ARCH.deb -O -L && \
    dpkg -i litestream-0.5.0-linux-$ARCH.deb

ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:$PATH"

RUN uv tool install "dstack[all]==$VERSION"

COPY entrypoint.sh entrypoint.sh
RUN chmod 777 entrypoint.sh

EXPOSE 3000

ENTRYPOINT ["/usr/bin/tini", "--", "./entrypoint.sh"]
