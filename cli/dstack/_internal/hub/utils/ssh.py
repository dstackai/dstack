from pathlib import Path

from dstack._internal.utils.crypto import generage_rsa_key_pair

HUB_PRIVATE_KEY_PATH = Path.home() / ".dstack" / "hub" / "ssh" / "hub_ssh_key"
HUB_PUBLIC_KEY_PATH = Path.home() / ".dstack" / "hub" / "ssh" / "hub_ssh_key.pub"


def generate_hub_ssh_key_pair():
    if HUB_PRIVATE_KEY_PATH.exists():
        return
    HUB_PRIVATE_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    generage_rsa_key_pair(
        private_key_path=HUB_PRIVATE_KEY_PATH, public_key_path=HUB_PUBLIC_KEY_PATH
    )


def get_hub_ssh_public_key() -> str:
    with open(HUB_PUBLIC_KEY_PATH) as f:
        return f.read()
