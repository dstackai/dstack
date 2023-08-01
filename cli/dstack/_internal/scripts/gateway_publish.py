import argparse
import re
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

owner = "www-data"


def main():
    parser = argparse.ArgumentParser(prog="gateway_publish.py")
    parser.add_argument("hostname", help="IP address or domain name")
    parser.add_argument("port", type=int, help="Public port")
    parser.add_argument("ssh_key", help="Public ssh key")
    args = parser.parse_args()

    # detect conflicts
    conf_path = Path("/etc/nginx/sites-enabled") / f"{args.port}-{args.hostname}.conf"
    if conf_path.exists() and is_conf_active(conf_path):
        exit(f"{args.hostname}:{args.port} is still in use")

    # create temp dir for socket
    temp_dir = tempfile.mkdtemp(prefix="dstack-")
    shutil.chown(temp_dir, user=owner, group=owner)
    sock_path = Path(temp_dir) / "http.sock"
    print(sock_path)

    # write nginx configuration
    upstream = Path(temp_dir).name
    conf = format_nginx_conf(
        {
            f"upstream {upstream}": {
                "server": f"unix:{sock_path}",
            },
            "server": {
                "server_name": args.hostname,
                "listen": args.port,
                "location /": {
                    "proxy_pass": f"http://{upstream}",
                    "proxy_set_header X-Real-IP": "$remote_addr",
                    "proxy_set_header Host": "$host",
                },
            },
        }
    )
    conf_path.write_text(conf)
    reload_nginx()

    # add ssh-key
    add_ssh_key(args.ssh_key)


def is_conf_active(conf_path: Path) -> bool:
    r = re.search(r"server unix:([^;]+/http\.sock);", conf_path.read_text())
    if r is None:
        raise ValueError("No http.sock in conf file")
    sock_path = r.group(1)
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(sock_path)
    except FileNotFoundError:
        # WARNING: possible race condition if the first job hasn't started yet, but we can't return True,
        # because the first job could fail to start preventing reusing this hostname
        return False
    except ConnectionRefusedError:
        return False
    return True


def format_nginx_conf(o: dict, *, indent=2, depth=0) -> str:
    pad = " " * depth * indent
    text = ""
    for key, value in o.items():
        if isinstance(value, dict):
            text += pad + key + " {\n"
            text += format_nginx_conf(value, indent=indent, depth=depth + 1)
            text += pad + "}\n"
        else:
            text += pad + f"{key} {value};\n"
    return text


def reload_nginx():
    if subprocess.run(["systemctl", "reload", "nginx.service"]).returncode != 0:
        exit("Failed to reload nginx")


def add_ssh_key(ssh_key: str):
    authorized_keys = Path("/var/www/.ssh/authorized_keys")
    if not authorized_keys.exists():
        exit(f"{authorized_keys} doesn't exist")
    with authorized_keys.open("a") as f:
        print(f'command="/bin/true" {ssh_key}', file=f)


if __name__ == "__main__":
    main()
