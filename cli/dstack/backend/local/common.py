import os
from typing import List, Optional
from pathlib import Path
import sqlite3

def list_objects(Root: str, Prefix: str, MaxKeys: Optional[int] = None) -> List[str]:
    if not os.path.exists(Root):
        return []
    files = os.listdir(Root)
    l = []
    count_keys = 0
    for file in files:
        if file.startswith(Prefix):
            if MaxKeys:
                if count_keys < MaxKeys:
                    break
            l.append(file)
            count_keys += 1
    return l


def put_object(Body: str, Root: str, Key: str):
    if not os.path.exists(Root):
        Path(Root).mkdir(parents=True)
    with open(os.path.join(Root, Key), 'w') as f:
        f.write(Body)


def get_object(Root: str, Key: str):
    if not os.path.exists(Root):
        raise IOError
    if not os.path.exists(os.path.join(Root, Key)):
        raise IOError
    with open(os.path.join(Root, Key)) as f:
        body = f.read()
    return body or ''


def delete_object(Root: str, Key: str):
    if not os.path.exists(Root):
        return
    path = os.path.join(Root, Key)
    if os.path.exists(path):
        os.remove(path)


def get_secret_value(SecretId: str, Root:str):
    _check_db(Root)
    path_db = os.path.join(Root, "_secrets_")
    con = sqlite3.connect(path_db)
    cur = con.cursor()
    cur.execute("SELECT secret_string FROM KV WHERE secret_name=?", (SecretId, ))
    value = cur.fetchone()
    con.close()
    if value:
        return value[0]
    return value

def update_secret(SecretId: str, SecretString: str, Root:str):
    _check_db(Root)
    path_db = os.path.join(Root, "_secrets_")
    con = sqlite3.connect(path_db)
    cur = con.cursor()
    cur.execute("UPDATE KV SET secret_string = ? WHERE secret_name=?", (SecretString, SecretId))
    con.commit()
    con.close()


def create_secret(SecretId: str, SecretString: str, Description: str, Root:str):
    _check_db(Root)
    path_db = os.path.join(Root, "_secrets_")
    con = sqlite3.connect(path_db)
    cur = con.cursor()
    cur.execute("INSERT INTO KV VALUES(?, ?)", (SecretId, SecretString))
    con.commit()
    con.close()


def put_secret_value(SecretId: str, SecretString: str, Root:str):
    _check_db(Root)
    path_db = os.path.join(Root, "_secrets_")
    con = sqlite3.connect(path_db)
    cur = con.cursor()
    cur.execute("UPDATE KV SET secret_string = ? WHERE secret_name=?", (SecretString, SecretId))
    con.commit()
    con.close()


def delete_secret(SecretId: str, Root:str):
    _check_db(Root)
    path_db = os.path.join(Root, "_secrets_")
    con = sqlite3.connect(path_db)
    cur = con.cursor()
    cur.execute("DELETE FROM KV WHERE secret_name=?", SecretId)
    con.commit()
    con.close()


def _check_db(Root: str):
    path_db = os.path.join(Root, "_secrets_")
    if not os.path.exists(Root):
        os.mkdir(Root)
    if not os.path.exists(path_db):
        con = sqlite3.connect(path_db)
        cur = con.cursor()
        cur.execute('''CREATE TABLE IF NOT EXISTS KV (secret_name TEXT, secret_string TEXT);''')
        con.commit()
        con.close()

