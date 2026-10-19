"""Cisco CIMC Redfish client.

Scope: just the operations needed to install ND on the bootstrap node:
  - session login/logout
  - find the CD/DVD virtual media slot
  - insert/eject ISO from an HTTP URL
  - one-time UEFI boot override to "Cisco CIMC-Mapped vDVD"
  - power on / off / force restart
  - read system serial number

TLS verification is enabled by default. Self-signed CIMC certs are common in lab;
pass ca_bundle=False (and accept the warning) only in non-production.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import requests
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

# Make shared/lib importable when scripts are run directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.lib.logging import get_logger  # noqa: E402

log = get_logger(__name__)


class RedfishError(RuntimeError):
    pass


class RedfishTransient(RedfishError):
    """Retryable CIMC response while its Redfish service is recovering."""


# UEFI boot target string the CVD uses for CIMC-mapped vDVD.
BOOT_TARGET_VDVD = "Cd"  # standard Redfish; CIMC maps this to the vDVD device


class CimcRedfish:
    """Thin Redfish client for one CIMC."""

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        *,
        verify: bool | str = True,
        timeout: int = 30,
    ) -> None:
        self.host = host
        self.base = f"https://{host}/redfish/v1"
        self.username = username
        self._password = password
        self.timeout = timeout
        self._verify: bool | str = verify
        self._token: str | None = None
        self._session_url: str | None = None
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json", "Accept": "application/json"})

    # ---------- session ----------

    @retry(
        retry=retry_if_exception_type((requests.RequestException, RedfishTransient)),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def login(self) -> None:
        r = self._session.post(
            f"{self.base}/SessionService/Sessions",
            json={"UserName": self.username, "Password": self._password},
            verify=self._verify,
            timeout=self.timeout,
        )
        if r.status_code in (400, 429) or r.status_code >= 500:
            raise RedfishTransient(
                f"login temporarily unavailable for {self.host}: "
                f"{r.status_code} {r.text[:200]}"
            )
        if r.status_code not in (200, 201):
            raise RedfishError(f"login failed for {self.host}: {r.status_code} {r.text[:200]}")
        token = r.headers.get("X-Auth-Token")
        if not token:
            raise RedfishError(f"login to {self.host} returned no X-Auth-Token")
        self._token = token
        self._session_url = r.headers.get("Location")
        self._session.headers["X-Auth-Token"] = token
        log.info("redfish login ok", extra={"event": "redfish.login", "node": self.host})

    def logout(self) -> None:
        if not self._session_url:
            return
        try:
            url = self._session_url
            if url.startswith("/"):
                url = f"https://{self.host}{url}"
            self._session.delete(url, verify=self._verify, timeout=self.timeout)
        except requests.RequestException as e:
            log.warning("redfish logout failed", extra={"event": "redfish.logout", "node": self.host, "err": str(e)})
        finally:
            self._token = None
            self._session_url = None
            self._session.headers.pop("X-Auth-Token", None)

    def refresh_session(self) -> None:
        """Replace a potentially expired token after a long-running install."""
        self.logout()
        self.login()
        log.info(
            "redfish session refreshed",
            extra={"event": "redfish.refresh", "node": self.host},
        )

    @contextmanager
    def session(self) -> Iterator["CimcRedfish"]:
        self.login()
        try:
            yield self
        finally:
            self.logout()

    @contextmanager
    def basic_session(self) -> Iterator["CimcRedfish"]:
        """Read-only fallback when CIMC refuses new token sessions.

        Some CIMC builds temporarily return a generic 400 from the Redfish
        SessionService after a host factory reset while HTTP Basic reads still
        work. Callers must use this fallback only for GET-based discovery;
        mutating operations continue to require a token session.
        """
        previous = self._session.auth
        self._session.auth = (self.username, self._password)
        try:
            yield self
        finally:
            self._session.auth = previous

    # ---------- low-level ----------

    def _url(self, path: str) -> str:
        """Resolve a Redfish reference into an absolute URL.

        Accepts three input shapes safely so callers don't have to care:
          1. Full URL ("http..."): returned as-is.
          2. Absolute service path ("/redfish/v1/..."): the host origin is
             prepended. This is the shape every `@odata.id` and action
             `target` from the server uses, so collection traversal works
             without doubling the prefix.
          3. Base-relative path ("/Systems", "/Managers/..."): joined with
             self.base. Used for hand-coded calls inside this client.
        """
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if path.startswith("/redfish/"):
            return f"https://{self.host}{path}"
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base}{path}"

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _get(self, path: str) -> dict[str, Any]:
        url = self._url(path)
        r = self._session.get(url, verify=self._verify, timeout=self.timeout)
        if r.status_code != 200:
            raise RedfishError(f"GET {url} -> {r.status_code} {r.text[:800]}")
        return r.json()

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _post(self, path: str, payload: dict[str, Any] | None = None) -> requests.Response:
        url = self._url(path)
        r = self._session.post(url, json=payload or {}, verify=self._verify, timeout=self.timeout)
        if r.status_code >= 400:
            raise RedfishError(f"POST {url} -> {r.status_code} {r.text[:800]}")
        return r

    @retry(
        retry=retry_if_exception_type(requests.RequestException),
        wait=wait_exponential(multiplier=2, min=2, max=20),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _patch(self, path: str, payload: dict[str, Any]) -> requests.Response:
        url = self._url(path)
        r = self._session.patch(url, json=payload, verify=self._verify, timeout=self.timeout)
        if r.status_code >= 400:
            raise RedfishError(f"PATCH {url} -> {r.status_code} {r.text[:800]}")
        return r

    # ---------- discovery ----------

    def system_id(self) -> str:
        systems = self._get("/Systems")
        members = systems.get("Members", [])
        if not members:
            raise RedfishError(f"{self.host}: no Systems found")
        odata = members[0]["@odata.id"]
        return odata.rsplit("/", 1)[-1]

    def system(self) -> dict[str, Any]:
        return self._get(f"/Systems/{self.system_id()}")

    def serial_number(self) -> str:
        sysinfo = self.system()
        sn = sysinfo.get("SerialNumber") or sysinfo.get("SKU")
        if not sn:
            raise RedfishError(f"{self.host}: SerialNumber not present")
        return sn

    def manager_id(self) -> str:
        mgrs = self._get("/Managers")
        members = mgrs.get("Members", [])
        if not members:
            raise RedfishError(f"{self.host}: no Managers found")
        return members[0]["@odata.id"].rsplit("/", 1)[-1]

    # ---------- virtual media ----------

    def _find_cd_slot(self) -> dict[str, Any]:
        mgr = self.manager_id()
        listing = self._get(f"/Managers/{mgr}/VirtualMedia")
        for m in listing.get("Members", []):
            slot = self._get(m["@odata.id"])
            media_types = slot.get("MediaTypes", []) or []
            if "CD" in media_types or "DVD" in media_types:
                return slot
        raise RedfishError(f"{self.host}: no CD/DVD virtual media slot found")

    def insert_iso(self, image_url: str) -> None:
        slot = self._find_cd_slot()
        # CIMC keeps the previous Image URL on the slot even after an eject,
        # and refuses InsertMedia if any non-empty Image is present (whether
        # currently inserted or not). Eject when either condition is true so
        # the operation is idempotent and tolerant of left-over state.
        if slot.get("Inserted") or slot.get("Image"):
            log.info("ejecting existing media",
                     extra={"event": "vmedia.eject", "node": self.host,
                            "currentImage": slot.get("Image"),
                            "inserted": slot.get("Inserted")})
            self._post(slot["Actions"]["#VirtualMedia.EjectMedia"]["target"])
        target = slot["Actions"]["#VirtualMedia.InsertMedia"]["target"]
        log.info("mounting ISO",
                 extra={"event": "vmedia.insert", "node": self.host, "url": image_url})
        # Cisco CIMC requires both TransferProtocolType and TransferMethod on
        # this firmware (SE-NODE-G2 / Redfish 1.5.1). "Stream" is the only
        # method supported for CIMC-mapped vMedia.
        self._post(target, {
            "Image": image_url,
            "TransferProtocolType": "HTTP",
            "TransferMethod": "Stream",
        })

    def eject_iso(self) -> None:
        slot = self._find_cd_slot()
        if not slot.get("Inserted") and not slot.get("Image"):
            return
        target = slot["Actions"]["#VirtualMedia.EjectMedia"]["target"]
        log.info("ejecting ISO",
                 extra={"event": "vmedia.eject", "node": self.host,
                        "currentImage": slot.get("Image")})
        self._post(target)

    # ---------- boot + power ----------

    def set_one_time_boot_vdvd(self) -> None:
        sid = self.system_id()
        log.info("setting one-time boot to vDVD",
                 extra={"event": "boot.override", "node": self.host})
        self._patch(f"/Systems/{sid}", {
            "Boot": {
                "BootSourceOverrideTarget": BOOT_TARGET_VDVD,
                "BootSourceOverrideEnabled": "Once",
                "BootSourceOverrideMode": "UEFI",
            }
        })

    def power_state(self) -> str:
        return self.system().get("PowerState", "Unknown")

    def power(self, action: str) -> None:
        """action: 'On' | 'ForceOff' | 'GracefulShutdown' | 'ForceRestart' | 'GracefulRestart'."""
        sid = self.system_id()
        log.info("power action",
                 extra={"event": "power", "node": self.host, "action": action})
        self._post(f"/Systems/{sid}/Actions/ComputerSystem.Reset", {"ResetType": action})

    def power_on(self) -> None:
        if self.power_state() == "On":
            return
        self.power("On")

    def power_off(self) -> None:
        if self.power_state() == "Off":
            return
        self.power("ForceOff")

    def force_restart(self) -> None:
        self.power("ForceRestart")
