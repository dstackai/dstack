from textwrap import dedent
from typing import Optional
from uuid import uuid4

from dstack._internal.core.errors import ComputeError
from dstack._internal.utils.logging import get_logger
from dstack._internal.utils.ssh import parse_public_key

logger = get_logger(__name__)


# Appended to the comment field of every authorized_keys entry added by the server. sshd
# ignores everything after the key blob, so the marker has no effect on authentication; it
# only records that the entry is ours.
#
# The shim adds its own entries, marked with `# added by dstack-shim`, and rewrites only the
# entries carrying that marker, see runner/internal/shim/authorized_keys.go. It matches the
# marker as an exact suffix, and this one is always appended last, therefore the entries added
# by this script are never touched by the shim. Do not change this value to anything that ends
# with the shim's marker.
DSTACK_PUBLIC_KEY_MARKER = "# added by dstack"


def build_authorized_keys(
    project_ssh_public_key: str,
    extra_authorized_keys: list[str],
) -> list[str]:
    """
    Builds the list of public keys to authorize on a job container.

    Args:
        project_ssh_public_key: The project public key, always authorized. Must be valid --
            the server cannot reach the container without it.
        extra_authorized_keys: The public keys to authorize in addition to the project key,
            as passed to `Compute.run_job()`. Untrusted -- keys that cannot be parsed are
            skipped with a warning, one bad key does not keep the rest out.

    Returns:
        The normalized keys in OpenSSH disk format, the project key first.

    Raises:
        ComputeError: The project key is invalid.
    """
    project_authorized_keys = normalize_authorized_keys([project_ssh_public_key])
    if not project_authorized_keys:
        raise ComputeError("Invalid project SSH key")
    return project_authorized_keys + normalize_authorized_keys(extra_authorized_keys)


def normalize_authorized_keys(authorized_keys: list[str]) -> list[str]:
    """
    Rebuilds the given public keys from their parsed fields.

    Every returned entry is a single `type blob [comment]` line with the comment whitespace
    normalized, so that nothing unvalidated reaches a command or a file.

    Args:
        authorized_keys: The public keys in OpenSSH disk format.

    Returns:
        The normalized keys, in the original order. Keys that cannot be parsed are skipped with
        a warning, therefore the result may be shorter than the input, or empty.
    """
    normalized: list[str] = []
    for authorized_key in authorized_keys:
        try:
            key = parse_public_key(authorized_key)
        except ValueError as e:
            logger.warning("Failed to parse authorized key: %r: %s", authorized_key, e)
            continue
        normalized.append(str(key))
    return normalized


def get_add_authorized_keys_script(
    authorized_keys: list[str],
    *,
    add_dstack_marker: bool = True,
    options: Optional[str] = None,
) -> str:
    """
    Builds a POSIX shell script adding the given public keys to `~/.ssh/authorized_keys`.

    The `~/.ssh` directory and the file are created if missing. An entry is added only if its
    key blob is not in the file yet, so the script can be run repeatedly; entries already in
    the file, whoever added them, are never modified or removed.

    Every entry is rebuilt from the parsed key, so that nothing unvalidated reaches the file.
    Keys that cannot be parsed are skipped with a warning -- one bad key does not keep the
    rest out of the file.

    The keys are passed to the script as heredoc data and never interpolated into commands,
    therefore the shell does not parse anything that came from a key.

    Args:
        authorized_keys: The public keys in OpenSSH disk format.
        add_dstack_marker: Whether to append DSTACK_PUBLIC_KEY_MARKER to every entry. Set to
            False only where the whole file is managed by dstack and there are no foreign
            entries to tell ours from.
        options: The authorized_keys options to prepend to every entry, e.g.
            `command="/bin/false"`. Must be a single line with no tabs.

    Returns:
        The script.
    """
    entries: list[str] = []
    for authorized_key in authorized_keys:
        try:
            key = parse_public_key(authorized_key)
        except ValueError as e:
            logger.warning("Failed to parse authorized key: %r: %s", authorized_key, e)
            continue
        entry = str(key)
        if add_dstack_marker:
            entry = f"{entry} {DSTACK_PUBLIC_KEY_MARKER}"
        if options is not None:
            entry = f"{options} {entry}"
        # The blob is the identity of the key -- the comment and the options are not, an entry
        # differing only in them is the same key and must not be added twice
        entries.append(f"{key.blob_base64}\t{entry}")
    eof = f"EOF_{uuid4().hex}"
    header = dedent(f"""\
        set -eu
        if [ ! -e ~/.ssh/authorized_keys ]; then
            mkdir -p ~/.ssh
            chmod 700 ~/.ssh
            touch ~/.ssh/authorized_keys
            chmod 600 ~/.ssh/authorized_keys
        elif [ -n "$(tail -c1 ~/.ssh/authorized_keys)" ]; then
            echo >> ~/.ssh/authorized_keys
        fi
        while IFS='\t' read -r blob entry <&3; do
            if ! grep -qF "$blob" ~/.ssh/authorized_keys; then
                echo "$entry" >> ~/.ssh/authorized_keys
            fi
        done 3<<'{eof}'""")
    return "\n".join([header, *entries, eof])
