from typing import Dict
from urllib.parse import urlunparse
import requests


def _url(scheme='', host='', path='', params='', query='', fragment=''):
    return urlunparse((scheme, host, path, params, query, fragment))


class HubClient:
    def __init__(self, host: str, port: str, token: str):
        pass

    @staticmethod
    def validate(host: str, token: str , port: str = "3000") -> bool:
        url = _url(scheme="http", host=f"{host}:{port}", path="api/auth/validate")
        try:
            resp = requests.get(url=url, headers=HubClient._auth(token=token))
            if resp.ok:
                return True
            if resp.status_code == 401:
                print("Unauthorized")
                return False
        except requests.ConnectionError:
            print(f"{host}:{port} connection refused")
        return False

    @staticmethod
    def _auth(token: str) -> Dict[str, str]:
        if token == "":
            return {}
        headers = {"Authorization": f"Bearer {token}"}
        return headers
