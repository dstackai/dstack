FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    software-properties-common \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --upgrade setuptools wheel && \
    pip3 install --upgrade fastapi  && \
    pip3 install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple "dstack[aws,gcp,azure]" -U

RUN if [ $(uname -m) = "aarch64" ]; then ARCH="arm64"; else ARCH="amd64"; fi && \
    curl https://github.com/benbjohnson/litestream/releases/download/v0.3.9/litestream-v0.3.9-linux-$ARCH.deb -O -L && \
    dpkg -i litestream-v0.3.9-linux-$ARCH.deb

EXPOSE 3000

ADD ./entry-point.sh /
RUN chmod 777 /entry-point.sh

ENTRYPOINT ["/bin/bash", "/entry-point.sh"]