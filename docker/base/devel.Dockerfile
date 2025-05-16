ARG PYTHON
ARG VERSION

FROM dstackai/base:py$PYTHON-$VERSION-cuda-12.1

RUN DEBIAN_FRONTEND=noninteractive apt-get install -y cuda-12-1
