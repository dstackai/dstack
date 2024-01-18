from typing import Dict, List, Optional

import kubernetes


def get_api(kubeconfig: Dict) -> kubernetes.client.CoreV1Api:
    api_client = kubernetes.config.new_client_from_config_dict(config_dict=kubeconfig)
    return kubernetes.client.CoreV1Api(api_client=api_client)


def get_cluster_public_ips(api_client: kubernetes.client.CoreV1Api) -> List[str]:
    public_ips = []
    for node in api_client.list_node().items:
        addresses = node.status.addresses

        # Look for an external IP address
        for address in addresses:
            if address.type == "ExternalIP":
                public_ips.append(address.address)

    return public_ips
