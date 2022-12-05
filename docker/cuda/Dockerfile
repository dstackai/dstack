FROM dstackai/cuda:11.1-base-ubuntu20.04

ARG PYTHON
ENV PYTHON=$PYTHON
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8
ENV PIP_ROOT_USER_ACTION=ignore

RUN apt-key adv --fetch-keys https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2004/x86_64/3bf863cc.pub &&  \
    apt-get update --fix-missing && \
    apt upgrade -y && \
    export DEBIAN_FRONTEND=noninteractive && \
    ln -fs /usr/share/zoneinfo/America/New_York /etc/localtime && \
    apt-get install -y tzdata && \
    dpkg-reconfigure --frontend noninteractive tzdata && \
    apt-get install -y wget bzip2 ca-certificates libglib2.0-0 libxext6 libsm6 libxrender1 git mercurial subversion

RUN wget -O Miniforge3.sh "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh" && \
    bash Miniforge3.sh -b -p "/root/conda" && \
    rm Miniforge3.sh && \
    ln -s /root/conda/etc/profile.d/conda.sh /etc/profile.d/conda.sh && \
    chmod +x /root/conda/etc/profile.d/conda.sh && \
    echo ". /root/conda/etc/profile.d/conda.sh" >> ~/.bashrc && \
    /root/conda/condabin/conda update conda --all -y && \
    /root/conda/condabin/conda create --name ${PYTHON} python=${PYTHON} -y && \
    echo "conda activate ${PYTHON}" >> ~/.bashrc