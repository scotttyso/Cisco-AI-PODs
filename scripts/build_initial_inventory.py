#!/usr/bin/env python3
"""Build an initial inventory from order spreadsheets."""

import argparse
import re
from pathlib import Path

import yaml
from openpyxl import load_workbook


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "host_vars/initial_inventory.ezai.yaml"
HEADERS = {"pid": "pid", "serial number": "serial_number", "mac addresses": "mac"}


class IndentedDumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, indentless=False)


def read_inventory(folder: Path) -> list[dict[str, str]]:
    files = sorted(folder.glob("*.xlsx"))
    if not files:
        raise ValueError(f"No .xlsx files found in {folder}")

    inventory = []
    found_headers = False
    for path in files:
        if path.name.startswith("~$"):
            continue
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            for sheet in workbook:
                columns = None
                for row_number, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                    if columns is None:
                        labels = {str(value).strip().casefold(): index for index, value in enumerate(row) if value is not None}
                        if all(header in labels for header in HEADERS):
                            columns = {key: labels[header] for header, key in HEADERS.items()}
                            found_headers = True
                        continue

                    mac = row[columns["mac"]] if len(row) > columns["mac"] else None
                    if mac is None or not str(mac).strip():
                        continue
                    mac_hex = re.sub(r"[:.-]", "", str(mac).strip())
                    if not re.fullmatch(r"[0-9a-fA-F]{12}", mac_hex):
                        raise ValueError(f"Invalid MAC address in {path.name}, {sheet.title}, row {row_number}: {mac}")
                    pid = row[columns["pid"]] if len(row) > columns["pid"] else None
                    serial = row[columns["serial_number"]] if len(row) > columns["serial_number"] else None
                    if not pid or not serial:
                        raise ValueError(f"Missing PID or serial number in {path.name}, {sheet.title}, row {row_number}")
                    if len(inventory) >= 254:
                        raise ValueError("More than 254 MAC entries; 198.18.0.X cannot hold them all")
                    inventory.append({
                        "hostname": "unknown",
                        "ip": f"198.18.0.{len(inventory) + 1}",
                        "mac": ":".join(mac_hex[index:index + 2] for index in range(0, 12, 2)).lower(),
                        "pid": str(pid).strip(),
                        "serial_number": str(serial).strip(),
                    })
        finally:
            workbook.close()

    if not found_headers:
        raise ValueError("No sheets contain PID, Serial number, and MAC Addresses columns")
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="YAML output path")
    arguments = parser.parse_args()

    default_folder = Path.home() / "orders"
    answer = input(f"Folder containing .xlsx files [{default_folder}]: ").strip()
    folder = Path(answer).expanduser() if answer else default_folder
    if not folder.is_dir():
        parser.error(f"Not a directory: {folder}")

    try:
        inventory = read_inventory(folder)
    except (OSError, ValueError) as error:
        parser.error(str(error))

    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("w", encoding="utf-8") as stream:
        yaml.dump({"initial_inventory": inventory}, stream, Dumper=IndentedDumper, sort_keys=False, explicit_start=True)
    print(f"Wrote {len(inventory)} entries to {arguments.output}")


if __name__ == "__main__":
    main()