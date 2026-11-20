import stat
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, rsa

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from aipod_webui import ssh_keys  # noqa: E402


def ed25519_pair():
    key = ed25519.Ed25519PrivateKey.generate()
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                serialization.NoEncryption()).decode()
    public = key.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH).decode()
    return private, public


def encrypted_pem():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.BestAvailableEncryption(b"secret")).decode()


def rsa_pem():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                             serialization.NoEncryption()).decode()


class ParseTests(unittest.TestCase):
    def test_openssh_and_pem_keys_are_read_and_their_public_key_derived(self):
        private, public = ed25519_pair()
        parsed = ssh_keys.parse_private_key(private)
        self.assertEqual((parsed.kind, parsed.public), ("ed25519", public))
        self.assertEqual(ssh_keys.parse_private_key(rsa_pem()).kind, "rsa")

    def test_unusable_input_is_rejected_with_a_reason(self):
        for text, expected in ((encrypted_pem(), "passphrase"), (ed25519_pair()[1], "not a private key"),
                               ("garbage", "not a private key"),
                               ("-----BEGIN PUBLIC KEY-----\nAAAA\n-----END PUBLIC KEY-----", "public key")):
            with self.assertRaises(ssh_keys.SshKeyError) as raised:
                ssh_keys.parse_private_key(text)
            self.assertIn(expected, str(raised.exception))

    def test_same_key_ignores_the_comment(self):
        self.assertTrue(ssh_keys.same_key("ssh-ed25519 AAAA one", "ssh-ed25519 AAAA two"))
        self.assertFalse(ssh_keys.same_key("ssh-ed25519 AAAA", "ssh-ed25519 BBBB"))


class InstallTests(unittest.TestCase):
    def test_key_is_installed_private_and_a_different_existing_key_is_backed_up(self):
        first, first_public = ed25519_pair()
        second, second_public = ed25519_pair()
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder) / ".ssh"
            notes = ssh_keys.install_key(first, first_public, directory)
            path = directory / "id_ed25519"
            self.assertIn(str(path), notes[0])
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
            self.assertEqual((directory / "id_ed25519.pub").read_text().split()[:2], first_public.split()[:2])
            self.assertIn("already holds", ssh_keys.install_key(first, first_public, directory)[0])
            notes = ssh_keys.install_key(second, second_public, directory)
            backups = list(directory.glob("id_ed25519.bak-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text().strip(), first.strip())
            self.assertEqual(stat.S_IMODE(backups[0].stat().st_mode), 0o600)
            self.assertTrue(any("kept as" in note for note in notes))
            self.assertEqual(ssh_keys.find_installed(second_public, directory), path)
            self.assertIsNone(ssh_keys.find_installed(first_public, directory))

    def test_job_installs_the_vault_key_and_warns_about_missing_or_mismatched_keys(self):
        private, public = ed25519_pair()
        other_public = ed25519_pair()[1]
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder) / ".ssh"
            warning = ssh_keys.install_from_environment({"ssh_public_key_1": public}, 1, directory)
            self.assertIn("WARNING", warning[0])
            notes = ssh_keys.install_from_environment({"ssh_public_key_1": public, "ssh_private_key_1": private}, 1, directory)
            self.assertTrue((directory / "id_ed25519").is_file())
            self.assertFalse(any("WARNING" in note for note in notes))
            self.assertIn("already in ~/.ssh", ssh_keys.install_from_environment({"ssh_public_key_1": public}, 1, directory)[0])
            mismatch = ssh_keys.install_from_environment(
                {"ssh_public_key_1": other_public, "ssh_private_key_1": private}, 1, directory)
            self.assertTrue(any("does not belong" in note for note in mismatch))
            self.assertEqual(ssh_keys.install_from_environment({}, None, directory), [])


if __name__ == "__main__":
    unittest.main()
