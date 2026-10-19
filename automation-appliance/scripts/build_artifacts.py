#!/usr/bin/env python3
"""Turn the Packer vSphere OVF export into a vApp-enabled OVA and an OpenShift Virtualization qcow2."""
import argparse
import hashlib
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

PROPERTIES = Path(__file__).with_name("ovf-properties.xml")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def add_vapp_properties(ovf, version):
    text = ovf.read_text()
    if "<ProductSection" not in text:
        closing = re.search(r"</(?:\w+:)?VirtualSystem>", text)
        if not closing:
            sys.exit(f"{ovf}: VirtualSystem element not found")
        product = PROPERTIES.read_text().replace("@VERSION@", version)
        text = text[:closing.start()] + product + text[closing.start():]
    if "com.vmware.guestInfo" not in text:
        # Deliver the OVF environment (vApp properties) to the guest through VMware Tools.
        text = re.sub(r"<((?:\w+:)?VirtualHardwareSection)\b", r'<\1 ovf:transport="com.vmware.guestInfo"',
                      text, count=1)
    ovf.write_text(text)
    return [ovf.parent / href for href in re.findall(r'ovf:href="([^"]+)"', text)]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export_dir", type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--skip-qcow2", action="store_true")
    arguments = parser.parse_args()

    ovfs = list(arguments.export_dir.glob("*.ovf"))
    if len(ovfs) != 1:
        sys.exit(f"Expected one .ovf in {arguments.export_dir}, found {len(ovfs)}")
    ovf = ovfs[0]
    references = add_vapp_properties(ovf, arguments.version)

    manifest = ovf.with_suffix(".mf")
    manifest.write_text("".join(f"SHA256({path.name})= {sha256(path)}\n" for path in [ovf, *references]))
    ova = arguments.export_dir.parent / f"{ovf.stem}-{arguments.version}.ova"
    # OVA members must be ordered: descriptor, manifest, then referenced files.
    with tarfile.open(ova, "w", format=tarfile.USTAR_FORMAT) as archive:
        for path in [ovf, manifest, *references]:
            archive.add(path, arcname=path.name)
    print(f"OVA:   {ova}")

    if arguments.skip_qcow2:
        return
    if not shutil.which("qemu-img"):
        print("qemu-img not found; skipping qcow2 conversion", file=sys.stderr)
        return
    disk = next((path for path in references if path.suffix == ".vmdk"), None)
    if disk is None:
        sys.exit("No VMDK referenced by the OVF")
    qcow2 = arguments.export_dir.parent / f"{ovf.stem}-{arguments.version}.qcow2"
    subprocess.run(["qemu-img", "convert", "-p", "-c", "-O", "qcow2", str(disk), str(qcow2)], check=True)
    print(f"qcow2: {qcow2}")


if __name__ == "__main__":
    main()
