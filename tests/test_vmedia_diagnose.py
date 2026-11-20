import datetime
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import vmedia_diagnose as tool  # noqa: E402


def slot_doc(state="Disabled", health="OK", inserted=False, image=None, message=""):
    status = {"State": state, "Health": health}
    if message:
        status["Health@Message.ExtendedInfo"] = [{"Message": message}]
    return {"Id": "3", "Name": "CIMC-Mapped vDVD", "Inserted": inserted, "Image": image, "Status": status}


class FakeFi:
    """Duck-typed Fi whose slot follows a scripted list of states."""

    def __init__(self, states):
        self.states, self.posts = list(states), []

    def get(self, _blade, _uri):
        return 200, self.states.pop(0) if len(self.states) > 1 else self.states[0]

    def post(self, _blade, uri, body):
        self.posts.append((uri.rsplit("/", 1)[-1], body))
        return 202, "{}"


class HelperTests(unittest.TestCase):
    def test_slot_summary_carries_the_cimc_message(self):
        slot = tool.slot_summary(slot_doc("UnavailableOffline", "Critical", message="Image file not found on server"))
        self.assertEqual((slot["state"], slot["health"], slot["message"]),
                         ("UnavailableOffline", "Critical", "Image file not found on server"))
        self.assertIn("file is not there", tool.hint_for(slot["message"]))
        self.assertIn("connection", tool.hint_for("Mount failed"))
        self.assertEqual(tool.hint_for("something else"), "")

    def test_access_log_requests_are_filtered_by_file_and_time_and_summarised(self):
        with tempfile.TemporaryDirectory() as folder:
            log = Path(folder) / "access.log"
            now = datetime.datetime.now().astimezone()
            old = (now - datetime.timedelta(hours=1)).strftime("%d/%b/%Y:%H:%M:%S %z")
            new = now.strftime("%d/%b/%Y:%H:%M:%S %z")
            log.write_text(
                f'10.0.0.1 - - [{old}] "GET /os-images/a.iso HTTP/1.1" 206 64 "-" "x" "-"\n'
                f'10.0.0.2 - - [{new}] "GET /os-images/a.iso HTTP/1.1" 206 64 "-" "x" "-"\n'
                f'10.0.0.2 - - [{new}] "HEAD /os-images/a.iso HTTP/1.1" 200 0 "-" "x" "-"\n'
                f'10.0.0.3 - - [{new}] "GET /os-images/b.iso HTTP/1.1" 200 1 "-" "x" "-"\n')
            found = tool.web_requests(log, "a.iso", now - datetime.timedelta(minutes=1))
            self.assertEqual(tool.summarize_requests(found), "10.0.0.2 GET 206 x1, 10.0.0.2 HEAD 200 x1")
            self.assertIsNone(tool.web_requests(Path(folder) / "missing.log", "a.iso", now))

    def test_server_json_selects_only_fi_servers_and_masks_the_password(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "server.json").write_text(json.dumps([
                {"hostname": "n1", "redfish": {"endpoint_type": "fi", "endpoint_ip": "10.0.0.5", "username": "admin",
                                               "password": "Sup3r!", "inventory_id": "r1-1-1"}},
                {"hostname": "hgx", "redfish": {"endpoint_type": "bmc", "endpoint_ip": "10.0.0.9", "password": "x"}}]))
            args = tool.parse_args(["inspect", "--dir", str(root)])
            clients, secrets = tool.build_clients(args)
            self.assertEqual([(fi.ip, blades) for fi, blades in clients], [("10.0.0.5", ["r1-1-1"])])
            printed = []
            with patch("builtins.print", lambda text, **_: printed.append(text)):
                tool.Output(secrets).line("login Sup3r! ok")
            self.assertEqual(printed, ["login ******** ok"])


class CaptureTests(unittest.TestCase):
    def verdict(self, text):
        return "\n".join(tool.summarize_capture(text, 443))

    def test_no_packets_means_the_path_is_the_problem(self):
        self.assertIn("path (route, VLAN, firewall)", self.verdict(""))

    def test_syn_without_answer_means_a_dropping_firewall_or_listener(self):
        self.assertIn("never answered", self.verdict("1.0 IP 10.0.0.2.5555 > 10.0.0.1.443: Flags [S], seq 1, length 0"))

    def test_connect_then_silence_and_a_bare_reset_are_told_apart(self):
        connected = ("1.0 IP 10.0.0.2.5555 > 10.0.0.1.443: Flags [S], seq 1, length 0\n"
                     "1.0 IP 10.0.0.1.443 > 10.0.0.2.5555: Flags [S.], seq 2, ack 2, length 0")
        self.assertIn("gave up right after connecting", self.verdict(connected))
        refused = "1.0 IP 10.0.0.1.443 > 10.0.0.2.5555: Flags [R.], seq 0, ack 2, length 0"
        self.assertIn("reset before any data", self.verdict(refused))

    def test_reset_after_data_points_at_tls(self):
        text = ("1.0 IP 10.0.0.2.5555 > 10.0.0.1.443: Flags [P.], seq 1:200, ack 1, length 199\n"
                "1.1 IP 10.0.0.1.443 > 10.0.0.2.5555: Flags [R.], seq 1, length 0")
        self.assertIn("TLS handshake", self.verdict(text))


class CaptureStartTests(unittest.TestCase):
    def test_capture_filter_uses_cimc_addresses_or_falls_back_to_connection_setup(self):
        with patch.object(tool.shutil, "which", return_value="/usr/sbin/tcpdump"), \
                patch.object(tool.subprocess, "Popen") as popen, patch.object(tool.time, "sleep", lambda _s: None):
            popen.return_value.poll.return_value = None
            _, note = tool.start_capture(["10.0.0.213", "10.0.0.214"], 443)
            self.assertEqual(note, "")
            self.assertIn("host 10.0.0.213 or host 10.0.0.214", popen.call_args.args[0][-1])
            _, note = tool.start_capture([], 443)
            self.assertIn("--cimc-ip", note)
            self.assertIn("tcp-syn", popen.call_args.args[0][-1])


class MountTests(unittest.TestCase):
    def run_mount(self, states, timeout=3):
        args = tool.parse_args(["mount", "--fi", "x", "--url", "https://h/os-images/a.iso", "--access-log", "/nonexistent",
                                "--timeout", str(timeout), "--interval", "0"])
        fi, lines = FakeFi(states), []
        out = tool.Output([])
        out.line = lines.append
        with patch.object(tool, "head_request", return_value="HEAD 200"), patch.object(tool.time, "sleep", lambda _s: None):
            ok = tool.mount_one(fi, "blade", args, out)
        return ok, "\n".join(lines), fi

    def test_successful_mount_is_reported_and_ejected_afterwards(self):
        ok, text, fi = self.run_mount([slot_doc(), slot_doc("Updating"), slot_doc("Enabled", inserted=True,
                                                                                 image="https://h/os-images/a.iso")])
        self.assertTrue(ok)
        self.assertEqual([name for name, _ in fi.posts], ["VirtualMedia.EjectMedia", "VirtualMedia.InsertMedia",
                                                           "VirtualMedia.EjectMedia"])
        self.assertEqual(fi.posts[1][1]["TransferProtocolType"], "HTTPS")

    def test_failed_mount_shows_the_cimc_message_and_its_meaning(self):
        ok, text, _ = self.run_mount([slot_doc(), slot_doc(), slot_doc("UnavailableOffline", "Critical", message="Mount failed")])
        self.assertFalse(ok)
        self.assertIn("message='Mount failed'", text)
        self.assertIn("meaning:", text)

    def test_slot_that_never_resolves_is_called_out(self):
        with patch.object(tool.time, "time", side_effect=[0, 0, 1, 99, 99, 99, 99, 99]):
            ok, text, _ = self.run_mount([slot_doc(), slot_doc(), slot_doc("Updating")], timeout=5)
        self.assertFalse(ok)
        self.assertIn("no result after", text)


if __name__ == "__main__":
    unittest.main()
