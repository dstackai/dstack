import os
import sqlite3
from pathlib import Path
from typing import List, Optional

from dstack.backend.base.secrets import SecretsManager
from dstack.core.repo import RepoAddress
from dstack.core.secret import Secret


class LocalSecretsManager(SecretsManager):
    def __init__(self, root_path: str):
        self.root_path = root_path

    def get_secret(self, repo_address: RepoAddress, secret_name: str) -> Optional[Secret]:
        value = _get_secret_value(
            db_filepath=_get_secrets_db_filepath(self.root_path, repo_address),
            key=_get_secret_key(repo_address, secret_name),
        )
        if value is None:
            return None
        return Secret(secret_name=secret_name, secret_value=value)

    def add_secret(self, repo_address: RepoAddress, secret: Secret):
        _create_secret(
            db_filepath=_get_secrets_db_filepath(self.root_path, repo_address),
            key=_get_secret_key(repo_address, secret.secret_name),
            value=secret.secret_value,
        )

    def update_secret(self, repo_address: RepoAddress, secret: Secret):
        _update_secret(
            db_filepath=_get_secrets_db_filepath(self.root_path, repo_address),
            key=_get_secret_key(repo_address, secret.secret_name),
            value=secret.secret_value,
        )

    def delete_secret(self, repo_address: RepoAddress, secret_name: str):
        _delete_secret(
            db_filepath=_get_secrets_db_filepath(self.root_path, repo_address),
            key=_get_secret_key(repo_address, secret_name),
        )

    def get_credentials(self, repo_address: RepoAddress) -> Optional[str]:
        return _get_secret_value(
            db_filepath=_get_credentials_db_filepath(self.root_path, repo_address),
            key=_get_credentials_key(repo_address),
        )

    def add_credentials(self, repo_address: RepoAddress, data: str):
        _create_secret(
            db_filepath=_get_credentials_db_filepath(self.root_path, repo_address),
            key=_get_credentials_key(repo_address),
            value=data,
        )

    def update_credentials(self, repo_address: RepoAddress, data: str):
        _update_secret(
            db_filepath=_get_credentials_db_filepath(self.root_path, repo_address),
            key=_get_credentials_key(repo_address),
            value=data,
        )


def _get_secret_value(db_filepath: str, key: str) -> Optional[str]:
    _check_db(db_filepath)
    con = sqlite3.connect(db_filepath)
    cur = con.cursor()
    cur.execute("SELECT secret_string FROM KV WHERE secret_name=?", (key,))
    value = cur.fetchone()
    con.close()
    if value is None:
        return None
    return value[0]


def _create_secret(db_filepath: str, key: str, value: str):
    _check_db(db_filepath)
    con = sqlite3.connect(db_filepath)
    cur = con.cursor()
    cur.execute("INSERT INTO KV VALUES(?, ?)", (key, value))
    con.commit()
    con.close()


def _update_secret(db_filepath: str, key: str, value: str):
    _check_db(db_filepath)
    con = sqlite3.connect(db_filepath)
    cur = con.cursor()
    cur.execute("UPDATE KV SET secret_string = ? WHERE secret_name=?", (value, key))
    con.commit()
    con.close()


def _delete_secret(db_filepath: str, key: str):
    _check_db(db_filepath)
    con = sqlite3.connect(db_filepath)
    cur = con.cursor()
    cur.execute("DELETE FROM KV WHERE secret_name=?", (key,))
    con.commit()
    con.close()


def _check_db(db_filepath: str):
    Path(db_filepath).parent.mkdir(exist_ok=True, parents=True)
    if not os.path.exists(db_filepath):
        con = sqlite3.connect(db_filepath)
        cur = con.cursor()
        cur.execute("""CREATE TABLE IF NOT EXISTS KV (secret_name TEXT, secret_string TEXT);""")
        con.commit()
        con.close()


def _get_secrets_db_filepath(root: str, repo_address: RepoAddress) -> str:
    return os.path.join(_get_secrets_dir(root, repo_address), "_secrets_")


def _get_secrets_dir(root: str, repo_address: RepoAddress) -> str:
    return os.path.join(root, "secrets", repo_address.path())


def _get_secret_key(repo_address: RepoAddress, secret_name: str) -> str:
    return f"/dstack/secrets/{repo_address.path()}/{secret_name}"


def _get_credentials_db_filepath(root: str, repo_address: RepoAddress) -> str:
    return os.path.join(root, "repos", "_secrets_")


def _get_credentials_key(repo_address: RepoAddress) -> str:
    return f"/dstack/credentials/{repo_address.path()}"
