#!/usr/bin/env python3
"""Collect Nexus switch identity data and update DHCP and fabric YAML."""

import argparse
import io
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

from ruamel.yaml import YAML


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DHCP_FILE = REPOSITORY_ROOT / "host_vars/dhcp/dhcp.yaml"
DEFAULT_FABRIC_FILE = (
    REPOSITORY_ROOT / "host_vars/nexus_dashboard/fabrics.ezai.yaml"
)
SWITCH_COMMANDS = (
    "terminal length 0 ; show interface mgmt0 ; show module ; "
    "show license host-id"
)


def make_yaml() -> YAML:
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.width = 4096
    yaml.explicit_start = True
    return yaml


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as stream:
        return make_yaml().load(stream)


def render_yaml(document) -> str:
    stream = io.StringIO()
    make_yaml().dump(document, stream)
    return stream.getvalue()


def get_switches(document) -> Dict[str, object]:
    switches = {}
    for fabric in document.get("fabrics", []):
        for switch in fabric.get("switches", []):
            ip = str(switch["ip"])
            if ip in switches:
                raise ValueError(
                    f"Switch IP {ip} occurs more than once in the fabric file"
                )
            switches[ip] = switch
    if not switches:
        raise ValueError("No switches found in the fabric file")
    return switches


def get_reservations(document) -> Dict[str, object]:
    reservations = {}
    for reservation in document.get("dhcp", {}).get("reservations", []):
        ip = str(reservation["ip"])
        if ip in reservations:
            raise ValueError(f"DHCP reservation IP {ip} occurs more than once")
        reservations[ip] = reservation
    return reservations


def make_askpass_helper(directory: Path, password_file: Path) -> Path:
    helper = directory / "askpass"
    quoted_password_path = shlex.quote(str(password_file))
    helper.write_text(
        "#!/bin/sh\n"
        'case "${1-}" in\n'
        '  *"Are you sure you want to continue connecting"*)\n'
        '    printf "\\n%s\\n" "$1" > /dev/tty || exit 1\n'
        '    printf "Verify host-key fingerprint; type yes: " > /dev/tty\n'
        '    IFS= read -r answer < /dev/tty || exit 1\n'
        '    printf "%s\\n" "$answer"\n'
        "    ;;\n"
        "  *)\n"
        f"    IFS= read -r password < {quoted_password_path} || exit 1\n"
        '    printf "%s\\n" "$password"\n'
        "    ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    helper.chmod(0o700)
    return helper


def run_switch_command(
    ip: str, username: str, helper: Path, timeout: int
) -> str:
    ssh = shutil.which("ssh")
    if not ssh:
        raise RuntimeError("OpenSSH client 'ssh' was not found in PATH")

    command = [
        ssh,
        "-o",
        "RSAMinSize=1024",
        "-o",
        f"ConnectTimeout={timeout}",
        "-o",
        "NumberOfPasswordPrompts=1",
        "-o",
        "PreferredAuthentications=keyboard-interactive,password",
        "-o",
        "PubkeyAuthentication=no",
        "-o",
        "BatchMode=no",
        f"{username}@{ip}",
        SWITCH_COMMANDS,
    ]
    environment = os.environ.copy()
    environment.pop("NEXUS_PASSWORD", None)
    environment["SSH_ASKPASS"] = str(helper)
    environment["SSH_ASKPASS_REQUIRE"] = "force"
    environment.setdefault("DISPLAY", "localhost:0")

    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout + 30,
            env=environment,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(
            f"SSH command timed out after {timeout + 30} seconds"
        ) from error

    output = result.stdout + "\n" + result.stderr
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"SSH exited with status {result.returncode}"
            + (f": {detail[:500]}" if detail else "")
        )
    return output


def parse_switch_output(output: str) -> Dict[str, str]:
    mac_match = re.search(
        r"\baddress:\s*((?:[0-9a-f]{4}\.){2}[0-9a-f]{4}|"
        r"(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2})",
        output,
        re.IGNORECASE,
    )
    if not mac_match:
        raise ValueError("could not find the mgmt0 hardware address")
    mac_hex = re.sub(
        r"[^0-9a-f]", "", mac_match.group(1), flags=re.IGNORECASE
    ).lower()
    if len(mac_hex) != 12:
        raise ValueError(
            "mgmt0 hardware address is not a 48-bit MAC address"
        )
    mac = ":".join(
        mac_hex[index:index + 2] for index in range(0, 12, 2)
    )

    serial_match = re.search(
        r"\bVDH\s*=\s*([A-Za-z0-9]+)", output, re.IGNORECASE
    )
    if not serial_match:
        raise ValueError(
            "could not find the VDH serial from 'show license host-id'"
        )

    model_matches = re.findall(
        r"^\s*\d+\s+\d+\s+.+?\b(N[0-9A-Z-]+)\s+(?:ok|active)\b",
        output,
        re.IGNORECASE | re.MULTILINE,
    )
    models = {model.upper() for model in model_matches}
    if len(models) != 1:
        raise ValueError(
            "could not determine one unique Nexus model from 'show module'"
        )

    return {
        "mac": mac,
        "serialNumber": serial_match.group(1),
        "model": models.pop(),
    }


def set_string_preserving_style(mapping, key: str, value: str) -> None:
    previous = mapping.get(key)
    if isinstance(previous, str) and type(previous) is not str:
        value = type(previous)(value)
    mapping[key] = value


def write_documents(documents: List[Tuple[Path, object]]) -> None:
    staged = []
    try:
        for path, document in documents:
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
            )
            temporary_path = Path(temporary_name)
            staged.append((temporary_path, path))
            os.fchmod(file_descriptor, stat.S_IMODE(path.stat().st_mode))
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
                stream.write(render_yaml(document))
                stream.flush()
                os.fsync(stream.fileno())
        for temporary_path, path in staged:
            os.replace(temporary_path, path)
    finally:
        for temporary_path, _ in staged:
            temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read Nexus switch identity data and update "
            "DHCP and fabric host vars."
        )
    )
    parser.add_argument(
        "--user", default="admin", help="Switch SSH username (default: admin)"
    )
    parser.add_argument("--dhcp-file", type=Path, default=DEFAULT_DHCP_FILE)
    parser.add_argument(
        "--fabric-file", type=Path, default=DEFAULT_FABRIC_FILE
    )
    parser.add_argument("--connect-timeout", type=int, default=10)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect and display data without writing YAML",
    )
    arguments = parser.parse_args()

    password = os.environ.get("NEXUS_PASSWORD")
    if not password:
        parser.error(
            "NEXUS_PASSWORD must be exported in the shell "
            "that runs this script"
        )
    if not sys.stdin.isatty():
        parser.error(
            "Run from an interactive terminal to verify new SSH host-key "
            "fingerprints"
        )
    if (
        not arguments.dhcp_file.is_file()
        or not arguments.fabric_file.is_file()
    ):
        parser.error(
            "Both the DHCP and fabric YAML files must exist"
        )

    try:
        fabric_document = load_yaml(arguments.fabric_file)
        dhcp_document = load_yaml(arguments.dhcp_file)
        switches = get_switches(fabric_document)
        reservations = get_reservations(dhcp_document)
        missing = sorted(set(switches) - set(reservations))
        if missing:
            raise ValueError(
                "No DHCP reservation for switch IP(s): " + ", ".join(missing)
            )

        results = {}
        failures = []
        with tempfile.TemporaryDirectory(
            prefix="nexus-switch-inventory-"
        ) as temporary_directory:
            private_directory = Path(temporary_directory)
            password_file = private_directory / "password"
            password_file.write_text(
                password + "\n", encoding="utf-8"
            )
            password_file.chmod(0o600)
            helper = make_askpass_helper(private_directory, password_file)

            for ip, switch in switches.items():
                hostname = switch.get("hostname", ip)
                print(f"Querying {hostname} ({ip})...", flush=True)
                try:
                    output = run_switch_command(
                        ip,
                        arguments.user,
                        helper,
                        arguments.connect_timeout,
                    )
                    results[ip] = parse_switch_output(output)
                except (RuntimeError, ValueError) as error:
                    failures.append(f"{ip} ({hostname}): {error}")

        if failures:
            for failure in failures:
                print(f"ERROR: {failure}", file=sys.stderr)
            print(
                "No YAML files were changed because not all "
                "switches succeeded.",
                file=sys.stderr,
            )
            return 1

        fabric_document = load_yaml(arguments.fabric_file)
        dhcp_document = load_yaml(arguments.dhcp_file)
        switches = get_switches(fabric_document)
        reservations = get_reservations(dhcp_document)
        for ip, values in results.items():
            if ip not in switches or ip not in reservations:
                raise ValueError(
                    f"Switch or DHCP reservation for {ip} changed "
                    "during collection"
                )
            set_string_preserving_style(
                switches[ip], "model", values["model"]
            )
            set_string_preserving_style(
                switches[ip], "serialNumber", values["serialNumber"]
            )
            set_string_preserving_style(
                reservations[ip], "mac", values["mac"]
            )

        print("\nCollected switch identity:")
        for ip, values in results.items():
            hostname = switches[ip].get("hostname", ip)
            print(
                f"{hostname} {ip}: MAC {values['mac']}, "
                f"model {values['model']}, "
                f"serial {values['serialNumber']}"
            )

        if arguments.dry_run:
            print("\nDry run: YAML files were not changed.")
        else:
            write_documents(
                [
                    (arguments.dhcp_file, dhcp_document),
                    (arguments.fabric_file, fabric_document),
                ]
            )
            print(
                "\nUpdated DHCP reservations and fabric switch data."
            )
        return 0
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
