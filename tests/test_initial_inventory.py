import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml
from openpyxl import Workbook


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("inventory_builder", ROOT / "scripts/build_initial_inventory.py")
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class InitialInventoryTests(unittest.TestCase):
    def test_mac_padding(self):
        self.assertEqual(builder.normalize_mac("abc123"), "00:00:00:ab:c1:23")
        self.assertEqual(builder.normalize_mac("AABB.CCDD.EEFF"), "aa:bb:cc:dd:ee:ff")
        for value in ("", "xyz", "1234567890123"):
            with self.assertRaises(ValueError):
                builder.normalize_mac(value)

    def test_multiple_workbooks(self):
        with tempfile.TemporaryDirectory() as folder:
            for position in range(1, 4):
                workbook = Workbook()
                workbook.active.append(["PID", "Serial number", "MAC Addresses"])
                workbook.active.append(["UCS-TEST", f"SERIAL-{position}", f"abc{position}"])
                workbook.save(Path(folder) / f"order-{position}.xlsx")
                workbook.close()
            rows = builder.read_inventory(Path(folder))
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[-1]["ip"], "198.18.0.3")
            self.assertEqual(rows[0]["mac"], "00:00:00:00:ab:c1")

    def test_shared_services_schema(self):
        settings = dict(dns_servers=["192.0.2.53"], dns_search_domains=["example.com"],
                        domain_name="example.com", ntp_servers=["0.pool.ntp.org"], timezone="UTC",
                        proxy_servers=dict(http_proxy="http://proxy.example.com:8080", username="user", password=1))
        self.assertEqual(builder.validate_shared_services(settings), [])
        self.assertEqual(builder.validate_shared_services({}), [])
        for invalid in ({"timezone": "Not/AZone"}, {"dns_servers": []},
                        {"proxy_servers": {"password": "literal-password"}},
                        {"unexpected": "value"}):
            self.assertTrue(builder.validate_shared_services(invalid))

    def test_generation_and_edits(self):
        row = dict(hostname="node-1", ip="192.0.2.10", mac="abc123", pid="UCS-TEST", serial_number="SERIAL-1")
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "inventory.yaml"
            builder.write_inventory([row], {"timezone": "UTC"}, output)
            document = yaml.safe_load(output.read_text())
            self.assertEqual(document["shared_services"], {"timezone": "UTC"})
            self.assertEqual(document["initial_inventory"][0]["hostname"], "node-1")
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            with self.assertRaises(ValueError):
                builder.build_inventory_document([row], [])
            with self.assertRaises(ValueError):
                builder.write_inventory([row, row], {}, output)
            self.assertEqual(yaml.safe_load(output.read_text()), document)


if __name__ == "__main__":
    unittest.main()