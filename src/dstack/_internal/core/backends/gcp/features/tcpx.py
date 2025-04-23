from typing import List


def get_backend_specific_commands_tcpxo() -> List[str]:
    return [
        "modprobe import-helper",
        "gcloud -q auth configure-docker us-docker.pkg.dev",
        # Install the nccl, nccl-net lib into /var/lib/tcpxo/lib64/.
        (
            "docker run --rm "
            "--name nccl-installer "
            "--pull=never "
            "--network=host "
            "--volume /var/lib:/var/lib "
            "us-docker.pkg.dev/gce-ai-infra/gpudirect-tcpxo/nccl-plugin-gpudirecttcpx-dev:v1.0.8-1 "
            "install --install-nccl"
        ),
        # Start FasTrak receive-datapath-manager
        (
            "docker run "
            "--name receive-datapath-manager "
            "--detach "
            "--pull=never "
            "--cap-add=NET_ADMIN "
            "--network=host "
            "--privileged "
            "--gpus all "
            "--volume /usr/lib32:/usr/local/nvidia/lib64 "
            "--volume /dev/dmabuf_import_helper:/dev/dmabuf_import_helper "
            "--env LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu "
            "us-docker.pkg.dev/gce-ai-infra/gpudirect-tcpxo/tcpgpudmarxd-dev:v1.0.14 "
            "--num_hops=2 --num_nics=8 --uid= --alsologtostderr"
        ),
    ]


def get_backend_specific_commands_tcpx() -> List[str]:
    return [
        "cos-extensions install gpu -- --version=latest",
        "sudo mount --bind /var/lib/nvidia /var/lib/nvidia",
        "sudo mount -o remount,exec /var/lib/nvidia",
        (
            "docker run "
            "--detach "
            "--pull=always "
            "--name receive-datapath-manager "
            "--privileged "
            "--cap-add=NET_ADMIN --network=host "
            "--volume /var/lib/nvidia/lib64:/usr/local/nvidia/lib64 "
            "--device /dev/nvidia0:/dev/nvidia0 --device /dev/nvidia1:/dev/nvidia1 "
            "--device /dev/nvidia2:/dev/nvidia2 --device /dev/nvidia3:/dev/nvidia3 "
            "--device /dev/nvidia4:/dev/nvidia4 --device /dev/nvidia5:/dev/nvidia5 "
            "--device /dev/nvidia6:/dev/nvidia6 --device /dev/nvidia7:/dev/nvidia7 "
            "--device /dev/nvidia-uvm:/dev/nvidia-uvm --device /dev/nvidiactl:/dev/nvidiactl "
            "--env LD_LIBRARY_PATH=/usr/local/nvidia/lib64 "
            "--volume /run/tcpx:/run/tcpx "
            "--entrypoint /tcpgpudmarxd/build/app/tcpgpudmarxd "
            "us-docker.pkg.dev/gce-ai-infra/gpudirect-tcpx/tcpgpudmarxd "
            '--gpu_nic_preset a3vm --gpu_shmem_type fd --uds_path "/run/tcpx" --setup_param "--verbose 128 2 0"'
        ),
        "sudo iptables -I INPUT -p tcp -m tcp -j ACCEPT",
        "docker run --rm -v /var/lib:/var/lib us-docker.pkg.dev/gce-ai-infra/gpudirect-tcpx/nccl-plugin-gpudirecttcpx install --install-nccl",
        "sudo mount --bind /var/lib/tcpx /var/lib/tcpx",
        "sudo mount -o remount,exec /var/lib/tcpx",
    ]
