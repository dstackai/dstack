import os
import stat
import subprocess
from pathlib import Path

import pytest

from dstack._internal.core.backends.base.authorized_keys import (
    DSTACK_PUBLIC_KEY_MARKER,
    get_add_authorized_keys_script,
)

ED25519_BLOB = "AAAAC3NzaC1lZDI1NTE5AAAAINOmx0T+hBRaJ6jCi21ZYe2NW3EZS8e0Mdwl+yZJt+kD"
ED25519_KEY = f"ssh-ed25519 {ED25519_BLOB}"
ECDSA_BLOB = (
    "AAAAE2VjZHNhLXNoYTItbmlzdHAyNTYAAAAIbmlzdHAyNTYAAABBBE8xPz2OD5CXgZyHY6D70lMVk5IZyiWQRw5h"
    "9HHFrsqMp0v7SKEp89dBKAEPhq2h/4LfTFuH3aycKs/oZpbFbWM="
)
ECDSA_KEY = f"ecdsa-sha2-nistp256 {ECDSA_BLOB}"

SCRIPT_TIMEOUT = 10


def entries(script: str) -> list[str]:
    """Returns the authorized_keys entries the script would add, in order."""
    lines = script.split("\n")
    heredoc_start = next(i for i, line in enumerate(lines) if line.startswith("done 3<<")) + 1
    # the last line is the heredoc terminator
    return [line.split("\t", 1)[1] for line in lines[heredoc_start:-1]]


class TestGetAddAuthorizedKeysScript:
    def test_appends_marker_to_comment(self):
        script = get_add_authorized_keys_script([f"{ED25519_KEY} dev@host"])

        assert entries(script) == [f"{ED25519_KEY} dev@host {DSTACK_PUBLIC_KEY_MARKER}"]

    def test_marker_is_the_whole_comment_if_the_key_has_none(self):
        script = get_add_authorized_keys_script([ED25519_KEY])

        assert entries(script) == [f"{ED25519_KEY} {DSTACK_PUBLIC_KEY_MARKER}"]

    def test_prepends_options(self):
        script = get_add_authorized_keys_script([ED25519_KEY], options='command="/bin/false"')

        assert entries(script) == [
            f'command="/bin/false" {ED25519_KEY} {DSTACK_PUBLIC_KEY_MARKER}'
        ]

    def test_normalizes_comment_whitespace(self):
        # a tab in a comment would otherwise break the tab-delimited heredoc
        script = get_add_authorized_keys_script([f"{ED25519_KEY} my\tlaptop  key"])

        assert entries(script) == [f"{ED25519_KEY} my laptop key {DSTACK_PUBLIC_KEY_MARKER}"]

    @pytest.mark.parametrize(
        "invalid_key",
        [
            "",
            "not a key",
            "ssh-ed25519",
            f"ssh-rsa {ED25519_BLOB}",
            # options are not a part of the on-disk public key format
            f'command="/bin/false" {ED25519_KEY}',
            # a second key smuggled in via a newline
            f"{ED25519_KEY} dev@host\nssh-rsa AAAAB3NzaC1yc2E evil",
        ],
    )
    def test_skips_invalid_keys(self, invalid_key: str):
        script = get_add_authorized_keys_script([invalid_key, ECDSA_KEY])

        assert entries(script) == [f"{ECDSA_KEY} {DSTACK_PUBLIC_KEY_MARKER}"]

    def test_no_keys(self):
        # the script still creates the file, it just adds nothing
        assert entries(get_add_authorized_keys_script([])) == []


def run_script(script: str, home: Path) -> None:
    result = subprocess.run(
        ["sh", "-c", script],
        env={"HOME": str(home), "PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        # a broken script must fail the test, not block it on the terminal
        stdin=subprocess.DEVNULL,
        timeout=SCRIPT_TIMEOUT,
    )
    assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


def read_authorized_keys(home: Path) -> str:
    return (home / ".ssh" / "authorized_keys").read_text()


def write_authorized_keys(home: Path, content: str) -> None:
    (home / ".ssh").mkdir(exist_ok=True)
    (home / ".ssh" / "authorized_keys").write_text(content)


class TestAddAuthorizedKeysScriptExecution:
    def test_creates_ssh_dir_and_file(self, tmp_path: Path):
        run_script(get_add_authorized_keys_script([f"{ED25519_KEY} dev@host"]), tmp_path)

        assert read_authorized_keys(tmp_path) == (
            f"{ED25519_KEY} dev@host {DSTACK_PUBLIC_KEY_MARKER}\n"
        )
        assert stat.S_IMODE((tmp_path / ".ssh").stat().st_mode) == 0o700
        assert stat.S_IMODE((tmp_path / ".ssh" / "authorized_keys").stat().st_mode) == 0o600

    def test_creates_file_without_keys(self, tmp_path: Path):
        run_script(get_add_authorized_keys_script([]), tmp_path)

        assert read_authorized_keys(tmp_path) == ""

    def test_keeps_existing_entries(self, tmp_path: Path):
        write_authorized_keys(tmp_path, f"{ECDSA_KEY} added-by-hand\n")

        run_script(get_add_authorized_keys_script([f"{ED25519_KEY} dev@host"]), tmp_path)

        assert read_authorized_keys(tmp_path) == (
            f"{ECDSA_KEY} added-by-hand\n{ED25519_KEY} dev@host {DSTACK_PUBLIC_KEY_MARKER}\n"
        )

    def test_adds_newline_to_file_not_ending_with_one(self, tmp_path: Path):
        write_authorized_keys(tmp_path, f"{ECDSA_KEY} added-by-hand")

        run_script(get_add_authorized_keys_script([f"{ED25519_KEY} dev@host"]), tmp_path)

        assert read_authorized_keys(tmp_path) == (
            f"{ECDSA_KEY} added-by-hand\n{ED25519_KEY} dev@host {DSTACK_PUBLIC_KEY_MARKER}\n"
        )

    def test_is_idempotent(self, tmp_path: Path):
        script = get_add_authorized_keys_script([f"{ED25519_KEY} dev@host", ECDSA_KEY])

        run_script(script, tmp_path)
        run_script(script, tmp_path)

        assert read_authorized_keys(tmp_path) == (
            f"{ED25519_KEY} dev@host {DSTACK_PUBLIC_KEY_MARKER}\n"
            f"{ECDSA_KEY} {DSTACK_PUBLIC_KEY_MARKER}\n"
        )

    def test_does_not_add_a_key_already_in_the_file(self, tmp_path: Path):
        # the same key with another comment and no marker is still the same key
        write_authorized_keys(tmp_path, f"{ED25519_KEY} added-by-hand\n")

        run_script(get_add_authorized_keys_script([f"{ED25519_KEY} dev@host"]), tmp_path)

        assert read_authorized_keys(tmp_path) == f"{ED25519_KEY} added-by-hand\n"

    def test_writes_comment_with_shell_metacharacters_verbatim(self, tmp_path: Path):
        # the comment is passed to the script as data, so the shell does not parse it
        home = tmp_path / "home"
        home.mkdir()
        touched = tmp_path / "touched"
        comment = f"x';touch {touched};'"

        run_script(get_add_authorized_keys_script([f"{ED25519_KEY} {comment}"]), home)

        assert not touched.exists()
        assert read_authorized_keys(home) == (
            f"{ED25519_KEY} {comment} {DSTACK_PUBLIC_KEY_MARKER}\n"
        )
