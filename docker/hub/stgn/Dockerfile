FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install setuptools wheel fastapi --upgrade --progress-bar off && \
    pip3 install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple "dstack[all]" --upgrade --progress-bar off

RUN if [ $(uname -m) = "aarch64" ]; then ARCH="arm64"; else ARCH="amd64"; fi && \
    curl https://github.com/benbjohnson/litestream/releases/download/v0.4.0-beta.2/litestream-80f8de4d9ed16b7ae6f607bde85d90916784de7d-linux-$ARCH.deb -O -L && \
    dpkg -i litestream-80f8de4d9ed16b7ae6f607bde85d90916784de7d-linux-$ARCH.deb

EXPOSE 3000

ADD ./stgn/entry-point.sh /
RUN chmod 777 /entry-point.sh

ENTRYPOINT ["/bin/bash", "/entry-point.sh"]