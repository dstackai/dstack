import subprocess
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from dstack._internal.compat import IS_WINDOWS
from dstack._internal.utils import crypto
from dstack._internal.utils.path import FilePath
from dstack._internal.utils.ssh import (
    PublicKey,
    check_required_ssh_version,
    find_ssh_util,
    include_ssh_config,
    normalize_path,
    parse_public_key,
    pkey_from_str,
    resolve_ssh_key,
    update_ssh_config,
)

pytestmark = pytest.mark.windows

PRIVATE_KEY = """\
-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW
QyNTUxOQAAACDTpsdE/oQUWieowottWWHtjVtxGUvHtDHcJfsmSbfpAwAAAJDfsiip37Io
qQAAAAtzc2gtZWQyNTUxOQAAACDTpsdE/oQUWieowottWWHtjVtxGUvHtDHcJfsmSbfpAw
AAAEDD+JQrRu/CGiOsZTV8yXAukWWMwQeJSsRZvS36UpQRvdOmx0T+hBRaJ6jCi21ZYe2N
W3EZS8e0Mdwl+yZJt+kDAAAAC3Rlc3RAZHN0YWNrAQI=
-----END OPENSSH PRIVATE KEY-----
"""
PUBLIC_KEY_BLOB = "AAAAC3NzaC1lZDI1NTE5AAAAINOmx0T+hBRaJ6jCi21ZYe2NW3EZS8e0Mdwl+yZJt+kD"
PUBLIC_KEY_NO_COMMENT = f"ssh-ed25519 {PUBLIC_KEY_BLOB}"
PUBLIC_KEY = f"{PUBLIC_KEY_NO_COMMENT} test@dstack\n"
# A valid public key of a type paramiko cannot construct a PKey for
UNSUPPORTED_TYPE_PUBLIC_KEY = (
    "sk-ssh-ed25519@openssh.com AAAAGnNrLXNzaC1lZDI1NTE5QG9wZW5zc2guY29tAAAAIAABAgMEBQYHCAkKCwwN"
    "Dg8QERITFBUWFxgZGhscHR4fAAAABHNzaDo= test@dstack\n"
)


class TestNormalizePath:
    @pytest.mark.skipif(IS_WINDOWS, reason="POSIX OpenSSH home semantics")
    def test_does_not_collapse_path_under_overridden_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        identity_file = tmp_path / ".dstack" / "ssh" / "key"

        assert normalize_path(identity_file, collapse_user=True) == str(identity_file)

    @pytest.mark.skipif(IS_WINDOWS, reason="POSIX OpenSSH home semantics")
    def test_does_not_collapse_path_without_passwd_entry(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pwd.getpwuid", MagicMock(side_effect=KeyError))
        identity_file = tmp_path / ".dstack" / "ssh" / "key"

        assert normalize_path(identity_file, collapse_user=True) == str(identity_file)

    def test_collapses_path_under_openssh_home(self):
        identity_file = Path.home() / ".dstack" / "ssh" / "key"

        assert normalize_path(identity_file, collapse_user=True) == "~/.dstack/ssh/key"


@pytest.mark.skipif(IS_WINDOWS, reason="POSIX OpenSSH home semantics")
class TestTemporaryHomeSSHConfig:
    def test_writes_absolute_identity_file(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        identity_file = home / ".dstack" / "ssh" / "key"
        config_file = home / ".dstack" / "ssh" / "config"

        update_ssh_config(
            config_file,
            "test-run",
            {"IdentityFile": FilePath(identity_file)},
        )

        assert f"    IdentityFile {identity_file}\n" in config_file.read_text()

    def test_writes_absolute_include(self, tmp_path, monkeypatch):
        home = tmp_path / "home"
        monkeypatch.setenv("HOME", str(home))
        dstack_config = home / ".dstack" / "ssh" / "config"
        user_config = home / ".ssh" / "config"
        user_config.parent.mkdir(mode=0o700, parents=True)

        include_ssh_config(dstack_config, user_config)

        assert user_config.read_text() == f"Include {dstack_config}\n"


class TestCheckRequiredSSHVersion(unittest.TestCase):
    @patch("subprocess.run")
    def test_ssh_version_above_8_4(self, mock_run):
        # Mock subprocess.run to return a version above 8.4
        mock_run.return_value = MagicMock(returncode=0, stderr="OpenSSH_8.6p1, LibreSSL 3.3.6")

        self.assertTrue(check_required_ssh_version())

    @patch("subprocess.run")
    def test_ssh_version_below_8_4(self, mock_run):
        # Mock subprocess.run to return version 8.4
        mock_run.return_value = MagicMock(returncode=0, stderr="OpenSSH_8.2p1, LibreSSL 3.2.3")

        self.assertFalse(check_required_ssh_version())

    @patch("subprocess.run")
    def test_subprocess_error(self, mock_run):
        # Mock subprocess.run to raise a CalledProcessError
        mock_run.side_effect = subprocess.CalledProcessError(returncode=1, cmd="ssh -V")

        self.assertFalse(check_required_ssh_version())

    @patch("subprocess.run")
    def test_ssh_version_on_windows_above_8_4(self, mock_run):
        # Mock subprocess.run to return version 8.4
        mock_run.return_value = MagicMock(
            returncode=0, stdout="OpenSSH_for_Windows_8.7p1, LibreSSL 3.2.3", stderr=""
        )

        self.assertTrue(check_required_ssh_version())

    @patch("subprocess.run")
    def test_ssh_version_on_windows_below_8_4(self, mock_run):
        # Mock subprocess.run to return version 8.4
        mock_run.return_value = MagicMock(
            returncode=0, stdout="OpenSSH_for_Windows_8.1p1, LibreSSL 3.2.3", stderr=""
        )

        self.assertFalse(check_required_ssh_version())


class TestResolveSSHKey:
    def test_private_key_with_public_key_file(self, tmp_path: Path):
        private_key_path = tmp_path / "id_ed25519"
        private_key_path.write_text(PRIVATE_KEY)
        public_key_path = tmp_path / "id_ed25519.pub"
        public_key_path.write_text(PUBLIC_KEY)

        assert resolve_ssh_key(private_key_path) == (
            PUBLIC_KEY,
            public_key_path,
            PRIVATE_KEY,
            private_key_path,
        )

    def test_returns_public_key_file_contents_as_is(self, tmp_path: Path):
        private_key_path = tmp_path / "id_ed25519"
        private_key_path.write_text(PRIVATE_KEY)
        # A ".pub" file is not validated, its contents is passed through verbatim
        (tmp_path / "id_ed25519.pub").write_text("  not a key at all  ")

        public_key, _, _, _ = resolve_ssh_key(private_key_path)

        assert public_key == "  not a key at all  "

    def test_private_key_without_public_key_file(self, tmp_path: Path):
        private_key_path = tmp_path / "id_ed25519"
        private_key_path.write_text(PRIVATE_KEY)

        assert resolve_ssh_key(private_key_path) == (
            PUBLIC_KEY_NO_COMMENT,
            None,
            PRIVATE_KEY,
            private_key_path,
        )

    def test_public_key(self, tmp_path: Path):
        public_key_path = tmp_path / "id_ed25519.pub"
        public_key_path.write_text(PUBLIC_KEY)

        assert resolve_ssh_key(public_key_path) == (PUBLIC_KEY, public_key_path, None, None)

    def test_public_key_of_unsupported_type(self, tmp_path: Path):
        public_key_path = tmp_path / "id_sk_ed25519.pub"
        public_key_path.write_text(UNSUPPORTED_TYPE_PUBLIC_KEY)

        assert resolve_ssh_key(public_key_path) == (
            UNSUPPORTED_TYPE_PUBLIC_KEY,
            public_key_path,
            None,
            None,
        )

    def test_accepts_str_path(self, tmp_path: Path):
        private_key_path = tmp_path / "id_ed25519"
        private_key_path.write_text(PRIVATE_KEY)

        _, _, _, returned_path = resolve_ssh_key(str(private_key_path))

        assert returned_path == private_key_path

    @pytest.mark.skipif(IS_WINDOWS, reason="POSIX OpenSSH home semantics")
    def test_expands_user(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        private_key_path = tmp_path / "id_ed25519"
        private_key_path.write_text(PRIVATE_KEY)

        _, _, _, returned_path = resolve_ssh_key("~/id_ed25519")

        assert returned_path == private_key_path

    def test_finds_public_key_file_for_dotted_key_name(self, tmp_path: Path):
        private_key_path = tmp_path / "my.key"
        private_key_path.write_text(PRIVATE_KEY)
        public_key_path = tmp_path / "my.key.pub"
        public_key_path.write_text(PUBLIC_KEY)

        assert resolve_ssh_key(private_key_path) == (
            PUBLIC_KEY,
            public_key_path,
            PRIVATE_KEY,
            private_key_path,
        )

    @pytest.mark.skipif(find_ssh_util("ssh-keygen") is None, reason="requires ssh-keygen")
    def test_converts_pkcs8_private_key_to_pem(self, tmp_path: Path):
        # dstack generates PKCS#8 keys, paramiko only reads PEM and OpenSSH ones
        private_key_bytes, public_key_bytes = crypto.generate_rsa_key_pair_bytes()
        private_key_path = tmp_path / "id_rsa"
        private_key_path.write_bytes(private_key_bytes)

        public_key, public_key_path, private_key, _ = resolve_ssh_key(private_key_path)

        assert public_key_path is None
        assert public_key == public_key_bytes.decode().rsplit(" ", 1)[0]
        assert private_key.startswith("-----BEGIN RSA PRIVATE KEY-----")
        assert pkey_from_str(private_key)

    @pytest.mark.parametrize("contents", ["", "garbage", "ssh-ed25519 not-base64"])
    def test_raises_on_invalid_key(self, tmp_path: Path, contents: str):
        key_path = tmp_path / "id_ed25519"
        key_path.write_text(contents)

        with pytest.raises(ValueError, match="Unsupported key type or invalid key"):
            resolve_ssh_key(key_path)

    def test_raises_if_key_does_not_exist(self, tmp_path: Path):
        with pytest.raises(OSError):
            resolve_ssh_key(tmp_path / "id_ed25519")


class TestParsePublicKey:
    def test_key_with_comment(self):
        assert parse_public_key(PUBLIC_KEY) == PublicKey(
            type="ssh-ed25519", blob_base64=PUBLIC_KEY_BLOB, comment="test@dstack"
        )

    def test_key_without_comment(self):
        assert parse_public_key(PUBLIC_KEY_NO_COMMENT) == PublicKey(
            type="ssh-ed25519", blob_base64=PUBLIC_KEY_BLOB, comment=None
        )

    def test_accepts_unsupported_key_type(self):
        # any key type is accepted, even one paramiko cannot construct a PKey for
        key = parse_public_key(UNSUPPORTED_TYPE_PUBLIC_KEY)

        assert key.type == "sk-ssh-ed25519@openssh.com"
        # the blob is returned as is, with base64 padding preserved
        assert key.blob_base64 == UNSUPPORTED_TYPE_PUBLIC_KEY.split()[1]
        assert key.comment == "test@dstack"

    def test_normalizes_comment(self):
        key = parse_public_key(f"{PUBLIC_KEY_NO_COMMENT}   two \t words  \n")

        assert key.comment == "two words"

    def test_accepts_crlf_line_ending(self):
        key = parse_public_key(f"{PUBLIC_KEY_NO_COMMENT} test@dstack\r\n")

        assert key.comment == "test@dstack"

    @pytest.mark.parametrize("key", [PUBLIC_KEY, PUBLIC_KEY_NO_COMMENT])
    def test_str_round_trips(self, key: str):
        parsed = parse_public_key(key)

        assert str(parsed) == key.strip()
        assert parse_public_key(str(parsed)) == parsed

    @pytest.mark.parametrize("comment", [None, ""])
    def test_str_omits_absent_comment(self, comment: Optional[str]):
        key = PublicKey(type="ssh-ed25519", blob_base64=PUBLIC_KEY_BLOB, comment=comment)

        assert str(key) == PUBLIC_KEY_NO_COMMENT

    @pytest.mark.parametrize(
        ("key", "error"),
        [
            ("", "Expected a single line"),
            ("   ", "Expected a single line"),
            ("\n\n", "Expected a single line"),
            (PUBLIC_KEY + PUBLIC_KEY, "Expected a single line"),
            ("ssh-ed25519", "Not enough fields"),
            ("ssh-ed25519 not-base64!", "Failed to parse key"),
            # a stray non-base64 character that b64decode would otherwise discard silently,
            # yielding a valid blob but leaving the character in the returned key
            (f"ssh-ed25519 {PUBLIC_KEY_BLOB[:4]}!{PUBLIC_KEY_BLOB[4:]}", "Failed to parse key"),
            # the blob is shorter than the 4-byte type length prefix
            ("ssh-ed25519 AAA=", "Failed to parse key"),
            # the type field in the blob is not valid UTF-8
            ("ssh-ed25519 AAAABP////8=", "Failed to parse key"),
            (f"ssh-rsa {PUBLIC_KEY_BLOB}", "Key type mismatch"),
            # options are not supported, the first field is always read as a key type
            (f'command="/bin/false" {PUBLIC_KEY_NO_COMMENT}', "Failed to parse key"),
        ],
    )
    def test_raises_on_invalid_key(self, key: str, error: str):
        with pytest.raises(ValueError, match=error):
            parse_public_key(key)
