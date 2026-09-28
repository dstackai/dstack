import oci
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from dstack._internal.core.backends.oci.auth import get_signer, make_client_kwargs


@pytest.fixture
def key_file(tmp_path) -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = tmp_path / "oci_api_key.pem"
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return str(path)


@pytest.fixture
def token_file(tmp_path) -> str:
    path = tmp_path / "token"
    path.write_text("a.security.token\n")
    return str(path)


class TestGetSigner:
    def test_api_key_config_uses_the_sdk_default_signer(self, key_file: str):
        config = {
            "user": "ocid1.user.oc1..aaaa",
            "tenancy": "ocid1.tenancy.oc1..aaaa",
            "fingerprint": "00:11:22",
            "key_file": key_file,
            "region": "us-ashburn-1",
        }
        assert get_signer(config) is None
        assert make_client_kwargs(config) == {}

    def test_security_token_config_gets_a_security_token_signer(
        self, key_file: str, token_file: str
    ):
        config = {
            "tenancy": "ocid1.tenancy.oc1..aaaa",
            "fingerprint": "00:11:22",
            "key_file": key_file,
            "security_token_file": token_file,
            "region": "us-ashburn-1",
        }
        assert isinstance(get_signer(config), oci.auth.signers.SecurityTokenSigner)
        kwargs = make_client_kwargs(config)
        assert list(kwargs) == ["signer"]
        assert isinstance(kwargs["signer"], oci.auth.signers.SecurityTokenSigner)

    def test_security_token_is_stripped(self, key_file: str, token_file: str):
        config = {
            "tenancy": "ocid1.tenancy.oc1..aaaa",
            "key_file": key_file,
            "security_token_file": token_file,
            "region": "us-ashburn-1",
        }
        assert get_signer(config).api_key == "ST$a.security.token"
