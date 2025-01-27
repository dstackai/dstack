FROM nvidia/cuda:12.1.0-base-ubuntu20.04

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
    apt-get install -y bzip2 ca-certificates curl build-essential git libglib2.0-0 libsm6 libxext6 libxrender1 mercurial openssh-server subversion wget && \
    sed -i "s/.*PasswordAuthentication.*/PasswordAuthentication no/g" /etc/ssh/sshd_config && mkdir /run/sshd && \
    mkdir ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && rm /etc/ssh/ssh_host_*

RUN wget -O Miniforge3.sh "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-$(uname)-$(uname -m).sh" && \
    bash Miniforge3.sh -b -p "/opt/conda" && \
    rm Miniforge3.sh && \
    ln -s /opt/conda/etc/profile.d/conda.sh /etc/profile.d/conda.sh && \
    chmod +x /opt/conda/etc/profile.d/conda.sh && \
    echo ". /opt/conda/etc/profile.d/conda.sh" >> ~/.bashrc && \
    /opt/conda/condabin/conda update conda --all -y && \
    /opt/conda/condabin/conda create --name workflow python=${PYTHON} -y && \
    /opt/conda/condabin/conda config --prepend channels "nvidia/label/cuda-12.1.0" && \
    /opt/conda/condabin/conda config --set always_yes true && \
    /opt/conda/condabin/conda clean --all && \
    echo "conda activate workflow" >> ~/.bashrc
