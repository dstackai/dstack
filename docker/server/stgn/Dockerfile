FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV DSTACK_SERVER_LOG_FORMAT=json

WORKDIR /dstack-server

RUN apt-get update && apt-get install -y \
    curl \
    git \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

RUN if [ $(uname -m) = "aarch64" ]; then ARCH="arm64"; else ARCH="amd64"; fi && \
    curl https://github.com/benbjohnson/litestream/releases/download/v0.3.9/litestream-v0.3.9-linux-$ARCH.deb -O -L && \
    dpkg -i litestream-v0.3.9-linux-$ARCH.deb

ADD https://astral.sh/uv/install.sh /uv-installer.sh
RUN sh /uv-installer.sh && rm /uv-installer.sh
ENV PATH="/root/.local/bin/:$PATH"

COPY pyproject.toml uv.lock README.md ./
COPY src src
RUN uv sync --extra all

COPY docker/server/entrypoint.sh entrypoint.sh
RUN chmod 777 entrypoint.sh

EXPOSE 3000

ENTRYPOINT ["./entrypoint.sh"]
