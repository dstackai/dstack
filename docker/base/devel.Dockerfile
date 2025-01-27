ARG PYTHON
ARG VERSION

FROM dstackai/base:py$PYTHON-$VERSION-cuda-12.1

RUN /opt/conda/condabin/conda install --name workflow cuda -y && \
    /opt/conda/condabin/conda clean --all
