FROM python:3.11-slim

ARG VERSION
ENV VERSION=$VERSION
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install setuptools wheel fastapi --upgrade --progress-bar off && \
    pip3 install "dstack[all]==$VERSION" --progress-bar off

RUN if [ $(uname -m) = "aarch64" ]; then ARCH="arm64"; else ARCH="amd64"; fi && \
    curl https://github.com/benbjohnson/litestream/releases/download/v0.3.9/litestream-v0.3.9-linux-$ARCH.deb -O -L && \
    dpkg -i litestream-v0.3.9-linux-$ARCH.deb

EXPOSE 3000

ADD ./release/entry-point.sh /
RUN chmod 777 /entry-point.sh

ENTRYPOINT ["/bin/bash", "/entry-point.sh"]