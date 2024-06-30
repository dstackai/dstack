#!/bin/bash

# Setup script for NVIDIA TensorRT-LLM development environment

# Update package lists and install sudo
apt-get update && apt-get install -y sudo

# Add NVIDIA container toolkit repository
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Update package lists and install NVIDIA container toolkit and CMake
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit cmake

# Configure NVIDIA runtime for Docker
sudo nvidia-ctk runtime configure --runtime=docker

# Install Python and OpenMPI
sudo apt-get install -y apt-utils python3.10 python3-pip openmpi-bin libopenmpi-dev

# Uninstall existing PyTorch and TensorRT before installing TensorRT-LLM
pip uninstall -y torch tensorrt

# Install TensorRT-LLM
pip3 install tensorrt_llm -U --pre --extra-index-url https://pypi.nvidia.com
# pip3 install --extra-index-url https://pypi.nvidia.com/ tensorrt_llm==0.10.0

# Verify TensorRT-LLM installation
python3 -c "import tensorrt_llm"

# Install Hugging Face Hub
pip install huggingface_hub

# Install Git and Git LFS
sudo apt-get install -y git git-lfs
git lfs install

# Clone TensorRT-LLM repository
git clone https://github.com/NVIDIA/TensorRT-LLM.git
