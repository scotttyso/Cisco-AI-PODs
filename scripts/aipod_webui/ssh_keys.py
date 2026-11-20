"""SSH key pair handling for the OpenShift nodes.

iServer's post-install steps (SSH check, management node setup, day 2 tasks) log in as ``core`` with the private key
that belongs to the public key given at install time, and it looks for that private key in the profile of the user
running it (~/.ssh). So the private key has to be installed there: from the key the UI generates, or from one the
user uploads.
"""
from __future__ import annotations

import datetime
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

FILE_NAMES = {"ed25519": "id_ed25519", "rsa": "id_rsa", "ecdsa": "id_ecdsa"}
VAULT_PRIVATE = "ssh_private_key_{}"
VAULT_PUBLIC = "ssh_public_key_{}"


class SshKeyError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedKey:
    private: str
    public: str
    kind: str


def ssh_dir() -> Path:
    return Path.home() / ".ssh"


def parse_private_key(text: str) -> ParsedKey:
    """Validate a private key (OpenSSH or PEM, no passphrase) and derive its public key."""
    data = (text or "").strip().encode("utf-8")
    if not data.startswith(b"-----BEGIN"):
        raise SshKeyError("That is not a private key file (expected a line starting with -----BEGIN)")
    if b"PUBLIC KEY" in data.split(b"\n", 1)[0]:
        raise SshKeyError("That looks like a public key; upload the private key")
    key = None
    last: Exception | None = None
    for loader in (lambda: serialization.load_ssh_private_key(data, password=None),
                   lambda: serialization.load_pem_private_key(data, password=None)):
        try:
            key = loader()
            break
        except TypeError as error:
            raise SshKeyError("The private key is protected by a passphrase. iServer cannot answer a passphrase "
                              "prompt; remove it first (ssh-keygen -p -N '' -f <key>) or use Generate key pair") from error
        except (ValueError, UnsupportedAlgorithm) as error:  # another format or a damaged key; try the next loader
            last = error
    if key is None:
        raise SshKeyError(f"Could not read the private key ({type(last).__name__}); use an OpenSSH or PEM key "
                          "without a passphrase")
    if isinstance(key, ed25519.Ed25519PrivateKey):
        kind = "ed25519"
    elif isinstance(key, rsa.RSAPrivateKey):
        kind = "rsa"
    elif isinstance(key, ec.EllipticCurvePrivateKey):
        kind = "ecdsa"
    else:
        raise SshKeyError("Only ed25519, RSA and ECDSA keys are supported")
    public = key.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()
    return ParsedKey(data.decode("utf-8") + "\n", public, kind)


def same_key(first: str, second: str) -> bool:
    """True when two OpenSSH public keys are the same key (the comment is ignored)."""
    a, b = (first or "").split(), (second or "").split()
    return len(a) >= 2 and len(b) >= 2 and a[:2] == b[:2]


def _write(path: Path, text: str, mode: int) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(text)
    temporary.chmod(mode)
    os.replace(temporary, path)


def install_key(private: str, public: str, directory: Path | None = None) -> list[str]:
    """Install the key pair as ~/.ssh/id_<type> (0600) and id_<type>.pub (0644).

    A different key that is already there is kept as <name>.bak-<timestamp> (0600) before it is replaced."""
    parsed = parse_private_key(private)
    target_dir = Path(directory) if directory else ssh_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    target_dir.chmod(0o700)
    path = target_dir / FILE_NAMES[parsed.kind]
    notes = []
    if path.is_file():
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError:
            existing = ""
        if existing.strip() == parsed.private.strip():
            notes.append(f"{path} already holds this key")
            return notes
        stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        backup = path.with_name(f"{path.name}.bak-{stamp}")
        _write(backup, existing, 0o600)
        notes.append(f"the existing {path.name} was kept as {backup.name}")
    _write(path, parsed.private, 0o600)
    pub_text = (public or parsed.public).strip()
    if not same_key(pub_text, parsed.public):
        pub_text = parsed.public
    _write(path.with_name(path.name + ".pub"), pub_text + "\n", 0o644)
    notes.insert(0, f"private key installed as {path}")
    return notes


def find_installed(public: str, directory: Path | None = None) -> Path | None:
    """The ~/.ssh private key file that belongs to this public key, if any."""
    target_dir = Path(directory) if directory else ssh_dir()
    for name in FILE_NAMES.values():
        path = target_dir / name
        try:
            parsed = parse_private_key(path.read_text(encoding="utf-8"))
        except (OSError, SshKeyError):
            continue
        if same_key(parsed.public, public):
            return path
    return None


def install_from_environment(env: dict[str, str], number, directory: Path | None = None) -> list[str]:
    """Job side: install the vault's private key for ssh_public_key_<number>, or explain what is missing."""
    if number in (None, ""):
        return []
    private = env.get(VAULT_PRIVATE.format(number), "")
    public = env.get(VAULT_PUBLIC.format(number), "")
    if not private:
        if public and find_installed(public, directory):
            return [f"the private key for ssh_public_key_{number} is already in ~/.ssh"]
        return [f"WARNING: no private key is stored for ssh_public_key_{number} and none in ~/.ssh matches it. "
                "iServer's post-install SSH check will fail. Generate a key pair or upload the private key on "
                "Cluster Deployment > Node SSH key."]
    try:
        parsed = parse_private_key(private)
    except SshKeyError as error:
        return [f"WARNING: the stored private key for ssh_public_key_{number} is not usable: {error}"]
    notes = install_key(private, public, directory)
    if public and not same_key(public, parsed.public):
        notes.append(f"WARNING: ssh_public_key_{number} does not belong to the stored private key; the nodes will "
                     "get the public key but iServer will log in with the private key. Upload the matching private "
                     "key or generate a new pair.")
    return notes
