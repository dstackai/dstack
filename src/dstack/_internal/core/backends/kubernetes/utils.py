from typing import Dict, List, Optional

import kubernetes
import yaml


def get_api_from_config_data(kubeconfig_data: str) -> kubernetes.client.CoreV1Api:
    config_dict = yaml.load(kubeconfig_data, yaml.FullLoader)
    return get_api_from_config_dict(config_dict)


def get_api_from_config_dict(kubeconfig: Dict) -> kubernetes.client.CoreV1Api:
    api_client = kubernetes.config.new_client_from_config_dict(config_dict=kubeconfig)
    return kubernetes.client.CoreV1Api(api_client=api_client)


def get_cluster_public_ip(api_client: kubernetes.client.CoreV1Api) -> Optional[str]:
    """
    Returns public IP of any cluster node.
    """
    public_ips = get_cluster_public_ips(api_client)
    if len(public_ips) == 0:
        return None
    return public_ips[0]


def get_cluster_public_ips(api_client: kubernetes.client.CoreV1Api) -> List[str]:
    """
    Returns public IPs of all cluster nodes.
    """
    public_ips = []
    for node in api_client.list_node().items:
        addresses = node.status.addresses

        # Look for an external IP address
        for address in addresses:
            if address.type == "ExternalIP":
                public_ips.append(address.address)

    return public_ips
