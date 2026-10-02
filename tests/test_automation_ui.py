import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import automation_ui as web


class AutomationUiTests(unittest.TestCase):
    def test_password_change(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(web, "AUTH_FILE", Path(folder) / "users.json"):
            users = {"test": web.password_hash("original-password-123"), "other": web.password_hash("other-password-123")}
            web.write_private_file(web.AUTH_FILE, json.dumps(users))
            for current, new, confirmation in (("wrong", "replacement-password-123", "replacement-password-123"),
                                               ("original-password-123", "short", "short"),
                                               ("original-password-123", "replacement-password-123", "mismatch")):
                with self.assertRaises(ValueError):
                    web.change_password("test", current, new, confirmation)
                self.assertEqual(json.loads(web.AUTH_FILE.read_text()), users)
            web.change_password("test", "original-password-123", "replacement-password-123", "replacement-password-123")
            updated = json.loads(web.AUTH_FILE.read_text())
            self.assertTrue(web.password_matches("replacement-password-123", updated["test"]))
            self.assertFalse(web.password_matches("original-password-123", updated["test"]))
            self.assertEqual(users["other"], updated["other"])
            self.assertEqual(web.AUTH_FILE.stat().st_mode & 0o777, 0o600)

    def test_media_paths_and_listing(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(web, "MEDIA_DIR", Path(folder)):
            for name in ("../outside.iso", "/tmp/outside.iso", "folder/file.iso", "folder\\file.iso", ".upload.part", ""):
                with self.assertRaises(ValueError):
                    web.media_path(name)
            (web.MEDIA_DIR / "test.iso").write_bytes(b"test")
            (web.MEDIA_DIR / ".upload.part").write_bytes(b"temporary")
            (web.MEDIA_DIR / "subfolder").mkdir()
            (web.MEDIA_DIR / "link.iso").symlink_to(web.MEDIA_DIR / "test.iso")
            with self.assertRaises(ValueError):
                web.media_path("link.iso")
            self.assertEqual([row["name"] for row in web.list_media()], ["test.iso"])

    def test_list_inputs(self):
        self.assertEqual(web.split_values("192.0.2.1, 192.0.2.2\n192.0.2.3"),
                         ["192.0.2.1", "192.0.2.2", "192.0.2.3"])

    def test_manual_inventory_defaults(self):
        first = web.new_inventory_row([])
        second = web.new_inventory_row([first])
        self.assertEqual(first["ip"], "198.18.0.1")
        self.assertEqual(second["ip"], "198.18.0.2")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(first["mac"], "")
        self.assertEqual(web.new_inventory_row([dict(ip=f"198.18.0.{position}") for position in range(1, 255)])["ip"], "")

    def test_array_input_values(self):
        field = object.__new__(web.ArrayInput)
        from types import SimpleNamespace
        field.fields = [SimpleNamespace(value=" 192.0.2.1 "), SimpleNamespace(value=""),
                        SimpleNamespace(value="  "), SimpleNamespace(value="192.0.2.2")]
        self.assertEqual(field.value, ["192.0.2.1", "192.0.2.2"])


if __name__ == "__main__":
    unittest.main()