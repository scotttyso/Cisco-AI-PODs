#!/usr/bin/env python3
"""Stream a pinned, SHA512-verified NX-OS image into ND.

This helper is invoked by 03_sg2_software_upgrade.yml. It never retries a
write; after any ambiguous outcome, inspect the ND image repository first.
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import secrets
import time
import warnings

import requests
import yaml


IMAGE_NAME = "nxos64-s1.10.6.4.M.bin"
IMAGE_SIZE = 3_430_233_088
# Cisco Software Download's published SHA512 for the 10.6(4)M SG2 image.
IMAGE_SHA512 = (
    "4e30bf02a82d533a45f1f12b362d2dd517b48adf2d54f4bf174e3ffc7e042c"
    "7a8b45c85ca29068e87690194f4b3e85e0e2b985bebf0bf94bcafa3d49fb74cf27"
)


def select_profile(profile: str) -> None:
    """Select only vetted Cisco images with published byte size and SHA-512."""
    global IMAGE_NAME, IMAGE_SIZE, IMAGE_SHA512
    if profile == "sg2":
        return
    if profile != "cs":
        raise RuntimeError("Unsupported NX-OS image profile")
    IMAGE_NAME = "nxos64-cs.10.6.4.M.bin"
    IMAGE_SIZE = 2_962_740_224
    IMAGE_SHA512 = (
        "4ae1475c454918798679016c25e65fdca9205d310888efb80ddde9bf2cf94c98"
        "0822f49f44c9d3c85c50eb9ca1b475695689cd41fa54e0cde0c826d6bb707223"
    )


class MultipartStream:
    """File-like multipart body with a known length (never chunked)."""

    def __init__(self, image: pathlib.Path) -> None:
        self.source = image.open("rb")
        boundary = "aipod-" + secrets.token_hex(12)
        self.content_type = f"multipart/form-data; boundary={boundary}"
        self.prefix = memoryview(
            (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="fileName"; filename="{image.name}"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
        )
        self.suffix = memoryview((f"\r\n--{boundary}--\r\n").encode())
        self.length = len(self.prefix) + IMAGE_SIZE + len(self.suffix)
        self.sent = 0
        self.reported = 0

    def __len__(self) -> int:
        return self.length

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            size = 1024 * 1024
        if not size:
            return b""
        data = bytearray()
        if self.prefix:
            count = min(size, len(self.prefix))
            data += self.prefix[:count]
            self.prefix = self.prefix[count:]
        if len(data) < size and self.sent < IMAGE_SIZE:
            part = self.source.read(min(size - len(data), IMAGE_SIZE - self.sent))
            data += part
            self.sent += len(part)
            percent = self.sent * 100 // IMAGE_SIZE
            if percent >= self.reported + 10:
                self.reported = percent
                print(f"ND image stream {percent}% sent", flush=True)
        if len(data) < size and self.sent == IMAGE_SIZE and self.suffix:
            count = min(size - len(data), len(self.suffix))
            data += self.suffix[:count]
            self.suffix = self.suffix[count:]
        return bytes(data)

    def close(self) -> None:
        self.source.close()


def image_record(session: requests.Session, base: str) -> dict | None:
    response = session.get(base + "/api/v1/manage/fabricSoftware/images", timeout=(20, 45))
    if response.status_code != 200:
        raise RuntimeError(f"ND image-repository read returned HTTP {response.status_code}; body suppressed")
    matches = [
        item for item in response.json().get("uploadedImages", [])
        if item.get("imageName") == IMAGE_NAME
    ]
    if len(matches) > 1:
        raise RuntimeError("ND returned duplicate image names; refusing upload")
    return matches[0] if matches else None


def verify_local(image: pathlib.Path) -> None:
    if image.name != IMAGE_NAME or image.stat().st_size != IMAGE_SIZE:
        raise RuntimeError("Image filename or size differs from Cisco's published artifact")
    digest = hashlib.sha512()
    with image.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != IMAGE_SHA512:
        raise RuntimeError("Image SHA512 does not match Cisco's published value")
    print("Local image SHA512 verified against Cisco", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=pathlib.Path, required=True)
    parser.add_argument("--profile", choices=("sg2", "cs"), default="sg2")
    parser.add_argument("--vault", type=pathlib.Path, required=True)
    parser.add_argument("--nd-host", required=True)
    parser.add_argument("--verify-tls", action="store_true")
    args = parser.parse_args()
    select_profile(args.profile)
    verify_local(args.image)
    password = yaml.safe_load(args.vault.read_text()).get("vault_nd_admin_password")
    if not isinstance(password, str) or not password:
        raise RuntimeError("ND credential unavailable")
    base = "https://" + args.nd_host
    session = requests.Session()
    session.verify = args.verify_tls
    session.trust_env = False
    if not args.verify_tls:
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")
    try:
        login = session.post(
            base + "/api/v1/infra/login",
            json={"userName": "admin", "userPasswd": password, "domain": "DefaultAuth"},
            timeout=(20, 30),
        )
        if login.status_code != 200:
            raise RuntimeError(f"ND login returned HTTP {login.status_code}; body suppressed")
        existing = image_record(session, base)
        if existing:
            if existing.get("imagePresent") == "present" and existing.get("imageSize") == IMAGE_SIZE:
                print("Image already present in ND with expected size", flush=True)
                return 0
            raise RuntimeError("Image name exists in ND but is incomplete; inspect before any retry")
        body = MultipartStream(args.image)
        try:
            request = requests.Request(
                "POST", base + "/api/v1/manage/fabricSoftware/images",
                data=body, headers={"Content-Type": body.content_type},
            )
            prepared = session.prepare_request(request)
            if "Transfer-Encoding" in prepared.headers or prepared.headers.get("Content-Length") != str(len(body)):
                raise RuntimeError("Multipart framing invalid; refusing upload")
            print("Beginning one-shot ND image upload", flush=True)
            start = time.monotonic()
            try:
                response = session.send(prepared, timeout=(20, 3600))
            except requests.RequestException as exc:
                raise RuntimeError(
                    f"Upload outcome ambiguous ({type(exc).__name__}, "
                    f"{body.sent} of {IMAGE_SIZE} image bytes sent); "
                    "inspect ND before retry"
                ) from None
            print("ND upload HTTP", response.status_code, "seconds", round(time.monotonic() - start), flush=True)
            if response.status_code != 200:
                raise RuntimeError("ND rejected upload; response body suppressed; inspect repository")
        finally:
            body.close()
        # Large uploads can outlive ND's login lifetime. Refresh only the
        # authentication session; never resend the completed image POST.
        renewed = session.post(
            base + "/api/v1/infra/login",
            json={"userName": "admin", "userPasswd": password, "domain": "DefaultAuth"},
            timeout=(20, 30),
        )
        if renewed.status_code != 200:
            raise RuntimeError(
                f"ND login refresh returned HTTP {renewed.status_code}; "
                "inspect repository before any upload retry"
            )
        uploaded = image_record(session, base)
        if not uploaded or uploaded.get("imagePresent") != "present" or uploaded.get("imageSize") != IMAGE_SIZE:
            raise RuntimeError("ND did not register the complete image after upload")
        print("ND repository image verified", flush=True)
        return 0
    finally:
        try:
            session.post(base + "/api/v1/infra/logout", timeout=(20, 10))
        except requests.RequestException:
            pass
        session.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from None
