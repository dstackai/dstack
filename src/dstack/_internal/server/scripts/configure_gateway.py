import argparse
import json
import re
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

owner = "www-data"

# payload schema
# {
#     "authorized_key": "ssh-rsa ...",
#     "services": [
#         {
#             "hostname": "1.1.1.1",
#             "port": 80,
#             "secure": False,
#         }
#     ],
# }


def main():
    parser = argparse.ArgumentParser(prog="gateway_publish.py")
    parser.add_argument("payload", help="JSON encoded payload")
    args = parser.parse_args()

    payload = json.loads(args.payload)
    domains = []
    # pre-check conflicts
    for service in payload["services"]:
        if service["secure"]:
            if service["port"] != 443:
                exit("Only standard port 443 is allowed for HTTPS")
            domains.append(service["hostname"])
        elif service["port"] == 443:
            exit("Port 443 is reserved for HTTPS")

        # detect conflicts
        service["conf_path"] = (
            Path("/etc/nginx/sites-enabled") / f"{service['port']}-{service['hostname']}.conf"
        )
        if service["conf_path"].exists() and is_conf_active(service["conf_path"]):
            exit(
                f"Could not start the service, because {service['hostname']}:{service['port']} is in use"
            )
        # TODO check if the services are conflicting with each other
    if domains:
        run_certbot(domains)

    # create temp dir for sockets
    temp_dir = tempfile.mkdtemp(prefix="dstack-")
    shutil.chown(temp_dir, user=owner, group=owner)

    sock_paths = []
    # write new configs
    for i, service in enumerate(payload["services"]):
        sock_path = Path(temp_dir) / f"http{i}.sock"
        sock_paths.append(str(sock_path))

        upstream = f"{Path(temp_dir).name}{i}"
        conf = {
            f"upstream {upstream}": {
                "server": f"unix:{sock_path}",
            },
            "server": {
                "server_name": service["hostname"],
                "listen": service["port"],
                "location /": {
                    # the first location is required, always fallback to the @-location
                    "try_files": "/nonexistent @$http_upgrade",
                },
                "location @websocket": {
                    "proxy_pass": f"http://{upstream}",
                    "proxy_set_header X-Real-IP": "$remote_addr",
                    "proxy_set_header Host": "$host",
                    # web socket related headers
                    "proxy_http_version": "1.1",
                    "proxy_set_header Upgrade": "$http_upgrade",
                    "proxy_set_header Connection": '"Upgrade"',
                },
                "location @": {
                    "proxy_pass": f"http://{upstream}",
                    "proxy_set_header X-Real-IP": "$remote_addr",
                    "proxy_set_header Host": "$host",
                },
            },
        }
        if service["secure"]:
            conf["server"].update(
                {
                    "listen": "80",
                    f"listen {service['port']}": "ssl",
                    "ssl_certificate": f"/etc/letsencrypt/live/{service['hostname']}/fullchain.pem",
                    "ssl_certificate_key": f"/etc/letsencrypt/live/{service['hostname']}/privkey.pem",
                    "include": "/etc/letsencrypt/options-ssl-nginx.conf",
                    "ssl_dhparam": "/etc/letsencrypt/ssl-dhparams.pem",
                    'if ($scheme != "https")': {
                        "return": "301 https://$host$request_uri",
                    },
                }
            )
        service["conf_path"].write_text(format_nginx_conf(conf))
    print(json.dumps(sock_paths))
    reload_nginx()

    add_ssh_key(payload["authorized_key"])


def is_conf_active(conf_path: Path) -> bool:
    r = re.search(r"server unix:([^;]+/http\d+\.sock);", conf_path.read_text())
    if r is None:
        raise ValueError("No httpX.sock in conf file")
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


def run_certbot(domains: List[str]):
    args = [
        "certbot",
        "certonly",
        "--non-interactive",
        "--agree-tos",
        "--register-unsafely-without-email",
        "--nginx",
    ]
    for domain in domains:
        args += ["--domain", domain]
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = proc.communicate()
    if proc.returncode != 0:
        exit(f"Certbot failed:\n{stderr.decode()}")


if __name__ == "__main__":
    main()
