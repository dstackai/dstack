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
