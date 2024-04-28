import argparse
import importlib.resources
import os
import pwd
import subprocess
from pathlib import Path

systemd_dir = Path("/etc/systemd/system")
service_name = "dstack.gateway"
service_path = systemd_dir / f"{service_name}.service"
working_dir = Path("/home/ubuntu/dstack")


def main():
    # requires sudo privileges
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(required=True)

    install_parser = subparsers.add_parser("install")
    install_parser.set_defaults(action=install_action)
    install_parser.add_argument("--run", action="store_true")

    args = parser.parse_args()

    args.action(args)


def install_action(args):
    user = pwd.getpwnam("ubuntu")
    uid, gid = user.pw_uid, user.pw_gid

    print("Writing service file...")
    service_file = importlib.resources.read_text(
        "dstack.gateway.resources.systemd", service_path.name
    )
    service_path.write_text(service_file.format(working_dir=working_dir.as_posix()))

    for script_name in ["start.sh", "update.sh"]:
        print(f"Writing {script_name} script...")
        script = importlib.resources.read_text("dstack.gateway.resources.systemd", script_name)
        script_path = working_dir / script_name
        script_path.write_text(script)
        os.chown(script_path, uid, gid)

    print("Reloading systemd daemon...")
    assert subprocess.run(["systemctl", "daemon-reload"]).returncode == 0

    print("Enabling service...")
    args = ["--now"] if args.run else []
    assert subprocess.run(["systemctl", "enable", service_name] + args).returncode == 0


if __name__ == "__main__":
    main()
