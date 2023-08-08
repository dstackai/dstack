import argparse
import re
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

owner = "www-data"


def main():
    parser = argparse.ArgumentParser(prog="gateway_publish.py")
    parser.add_argument("hostname", help="IP address or domain name")
    parser.add_argument("port", type=int, help="Public port")
    parser.add_argument("ssh_key", help="Public ssh key")
    parser.add_argument("--secure", action="store_true", help="Enable SSL")
    args = parser.parse_args()

    if args.secure and args.port != 443:
        exit("Only standard port 443 is allowed for HTTPS")
    if not args.secure and args.port == 443:
        exit("Port 443 is reserved for HTTPS")

    # detect conflicts
    conf_path = Path("/etc/nginx/sites-enabled") / f"{args.port}-{args.hostname}.conf"
    if conf_path.exists() and is_conf_active(conf_path):
        exit(f"Could not start the service, because {args.hostname}:{args.port} is in use")

    # create temp dir for socket
    temp_dir = tempfile.mkdtemp(prefix="dstack-")
    shutil.chown(temp_dir, user=owner, group=owner)
    sock_path = Path(temp_dir) / "http.sock"
    print(sock_path)

    # issue ssl certificate
    ssl = {}
    if args.secure:
        run_certbot(args.hostname)
        ssl = {
            "listen": "80",
            f"listen {args.port}": "ssl",
            "ssl_certificate": f"/etc/letsencrypt/live/{args.hostname}/fullchain.pem",
            "ssl_certificate_key": f"/etc/letsencrypt/live/{args.hostname}/privkey.pem",
            "include": "/etc/letsencrypt/options-ssl-nginx.conf",
            "ssl_dhparam": "/etc/letsencrypt/ssl-dhparams.pem",
            'if ($scheme != "https")': {
                "return": "301 https://$host$request_uri",
            },
        }

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
                **ssl,
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


def format_nginx_conf(
    o: Union[Dict[str, Any], List[Tuple[str, Any]]], *, indent=2, depth=0
) -> str:
    pad = " " * depth * indent
    text = ""
    pairs = o.items() if isinstance(o, dict) else o
    for key, value in pairs:
        if isinstance(value, (dict, list)):
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


def run_certbot(hostname: str):
    args = [
        "certbot",
        "certonly",
        "--non-interactive",
        "--agree-tos",
        "--register-unsafely-without-email",
        "--nginx",
        "--domain",
        hostname,
    ]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        exit(f"Certbot failed:\n{stderr.decode()}")


if __name__ == "__main__":
    main()
