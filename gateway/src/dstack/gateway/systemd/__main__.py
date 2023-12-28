import argparse
import importlib.resources
import subprocess
from pathlib import Path

systemd_dir = Path("/etc/systemd/system")
service_name = "dstack.gateway"
service_path = systemd_dir / f"{service_name}.service"
working_dir = Path("/home/ubuntu/dstack")


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(required=True)
    install_parser = subparsers.add_parser("install")
    install_parser.set_defaults(action=install_action)
    args = parser.parse_args()

    args.action(args)


def install_action(args):
    print("Writing service file...")
    service_file = importlib.resources.read_text(
        "dstack.gateway.systemd", f"resources/{service_path.name}"
    )
    service_path.write_text(service_file.format(working_dir=working_dir.as_posix()))

    for script_name in ["start.sh", "update.sh"]:
        print(f"Writing {script_name} script...")
        script = importlib.resources.read_text(
            "dstack.gateway.systemd", f"resources/{script_name}"
        )
        (working_dir / script_name).write_text(script)

    print("Reloading systemd daemon...")
    assert subprocess.run(["systemctl", "daemon-reload"]).returncode == 0

    print("Enabling service...")
    assert subprocess.run(["systemctl", "enable", service_name]).returncode == 0


if __name__ == "__main__":
    main()
