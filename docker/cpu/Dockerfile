FROM ubuntu:20.04

ARG PYTHON
ENV PYTHON=$PYTHON
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
ENV PIP_ROOT_USER_ACTION=ignore

RUN apt-get update --fix-missing && \
    apt upgrade -y && \
    export DEBIAN_FRONTEND=noninteractive && \
    ln -fs /usr/share/zoneinfo/America/New_York /etc/localtime && \
    apt-get install -y tzdata && \
    dpkg-reconfigure --frontend noninteractive tzdata && \
    apt-get install -y curl wget bzip2 ca-certificates libglib2.0-0 libxext6 libsm6 libxrender1 git mercurial subversion gcc

RUN wget -O Miniforge3.sh "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh" && \
    bash Miniforge3.sh -b -p "/opt/conda" && \
    rm Miniforge3.sh && \
    ln -s /opt/conda/etc/profile.d/conda.sh /etc/profile.d/conda.sh && \
    chmod +x /opt/conda/etc/profile.d/conda.sh && \
    echo ". /opt/conda/etc/profile.d/conda.sh" >> ~/.bashrc && \
    /opt/conda/condabin/conda update conda --all -y && \
    /opt/conda/condabin/conda create --name ${PYTHON} python=${PYTHON} -y && \
    echo "conda activate ${PYTHON}" >> ~/.bashrc