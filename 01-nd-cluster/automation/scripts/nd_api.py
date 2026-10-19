"""Nexus Dashboard 4.2.x REST client — cluster bring-up, nodes, status, config.

Endpoints and payload shapes here are verified against the public OpenAPI for
Nexus Dashboard Infrastructure v1 (release 4.2 and above) on Cisco DevNet:
  https://developer.cisco.com/docs/nexus-dashboard/latest/create-node
  https://developer.cisco.com/docs/nexus-dashboard/latest/get-cluster-status
  https://developer.cisco.com/docs/nexus-dashboard/latest/list-nodes
  https://developer.cisco.com/docs/nexus-dashboard/latest/authentication
  https://developer.cisco.com/docs/nexus-dashboard/latest/execute-logout

Items still marked "TODO ASSUMED" must be confirmed against the running
appliance's API Inspector (Help -> API Reference / `/help-center/swagger/`)
once nd-1 is reachable. The companion script `verify_endpoints.py` performs
that confirmation pass and prints any deltas.

Auth: this client uses the cookie auth scheme (`AuthCookie=<JWT>`) declared in
the OpenAPI `securitySchemes`. requests.Session() handles cookie storage and
re-presentation transparently. The `Authorization: Bearer <jwttoken>` scheme
also works (`http_signature` in the spec) but cookie auth is simpler and is
what the GUI uses, which keeps automation behavior aligned with operator
debugging via the browser.

Workspace rules: secrets are never logged (codeguard-0-logging) and are
never written to source (codeguard-1-hardcoded-credentials). All write paths
through `_request` honor `verify` (TLS cert validation) when supplied a CA
bundle path; `verify=False` is reserved for lab gear with self-signed certs.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared.lib.logging import get_logger  # noqa: E402

log = get_logger(__name__)


class NdApiError(RuntimeError):
    """Hard error: ND returned a non-retryable HTTP failure or invalid body."""


class NdApiTransient(RuntimeError):
    """Retryable error: 429 / 5xx / connection blip. Caught by tenacity."""


def cluster_nodes(cluster: dict[str, Any]) -> list[dict[str, Any]]:
    """Return node records from the ND 4.x cluster-status response.

    ND 4.3 uses ``nodeDetailsList``.  The alternate keys keep the client
    tolerant of older response shapes already supported by this module.
    """
    nodes = (
        cluster.get("nodeDetailsList")
        or cluster.get("nodes")
        or cluster.get("nodeList")
        or []
    )
    return nodes if isinstance(nodes, list) else []


def node_operational_state(node: dict[str, Any]) -> str:
    """Return a normalized node state from flat or ND 4.3 nested status."""
    status = node.get("status")
    if isinstance(status, dict):
        value = status.get("operationalState") or status.get("state")
    else:
        value = node.get("operationalState") or node.get("state") or status
    return str(value or "unknown")


# Verified live on ND 4.2.1.10 (192.0.2.7) — see logs/nd1-endpoint-discovery-*.log
# and logs/nd1-bootstrap-discovery-*.log.
#
# Important: ND 4.2 cluster bring-up uses the /bootstrap/* path family on the
# bootstrap (single-node) appliance, NOT /api/v1/infra/cluster/*. The infra v1
# /cluster/status path returns 404 until the cluster is fully bootstrapped, at
# which point we may switch to it for runtime cluster ops.
#
# Each value is a server-absolute path (no /api/v1/infra prefix). Any caller
# that needs a prefixed runtime path should use `_infra_url` explicitly.
ENDPOINTS = {
    # Auth (always at root, not under /api/v1/infra).
    "login":             "/login",                 # POST verified live
    "logout":            "/logout",                # POST verified live (200)
    "refresh":           "/refresh",               # POST per OpenAPI; not yet verified live

    # Cluster bring-up (pre-cluster, single-node bootstrap appliance).
    "bootstrap_cluster": "/bootstrap/cluster",     # GET verified, OPTIONS=GET,OPTIONS,POST
    "bootstrap_status":  "/bootstrap/status",      # GET verified ({bootstrapped, message})

    # Runtime cluster (post-bootstrap; expect 404 pre-cluster).
    "cluster_status":    "/cluster/status",        # used as suffix off /api/v1/infra
    "cluster_nodes":     "/cluster/nodes",         # used as suffix off /api/v1/infra

    # Platform v1 (legacy, may be present on 4.2.1 once cluster is up).
    "platform_cluster":  "/nexus/infra/api/platform/v1/clusters",
    "platform_externalips": "/nexus/infra/api/platform/v1/externalips",
}


@dataclass(frozen=True)
class NodePayload:
    """Logical node info; mapped to the createNode JSON schema by build_node_payload.

    `role` here is the ND API role enum (primary | secondary | standby). For a
    standard 3-node HA cluster the deployment guide labels nodes 1-3 as
    "Primary" in the GUI; the inventory passes that through.
    """
    hostname: str
    role: str            # "primary" | "secondary" | "standby"
    cimc_ip: str | None  # None for the bootstrap node (already installed via ISO)
    cimc_user: str | None
    cimc_pass: str | None
    mgmt_ip: str
    mgmt_mask: int
    mgmt_gw: str
    data_ip: str
    data_mask: int
    data_gw: str
    data_vlan: int | None = None


@dataclass(frozen=True)
class ClusterSpec:
    """Cluster-level config we POST to the platform `/clusters/{specName}` API
    after Node 1 is reachable but before adding Nodes 2/3."""
    name: str
    timezone: str
    dns_servers: list[str]
    dns_search: list[str]
    ntp_servers: list[str]              # plain hostnames (subagent A: simple list)
    proxy_skip: bool
    proxy_url: str | None
    proxy_ignore_hosts: list[str]


class NdApi:
    """Thin REST client. One instance per ND cluster (talk to the Node 1 mgmt IP)."""

    def __init__(
        self,
        host: str,
        admin_password: str,
        *,
        username: str,
        domain: str = "local",
        verify: bool | str = True,
        timeout: int = 30,
    ) -> None:
        self.host = host
        self.username = username
        self._password = admin_password
        self._domain = domain
        self.timeout = timeout
        self._verify: bool | str = verify
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self._jwt: str | None = None

    # ------------------------------------------------------------------ URLs

    @property
    def _root(self) -> str:
        return f"https://{self.host}"

    def _root_url(self, path: str) -> str:
        """Server-absolute path (login/logout/bootstrap/* live here in ND 4.2.x)."""
        return f"{self._root}{path}"

    @property
    def _infra_base(self) -> str:
        return f"{self._root}/api/v1/infra"

    def _infra_url(self, path: str) -> str:
        """Runtime infra v1 (cluster/status, cluster/nodes); 404 pre-cluster."""
        return f"{self._infra_base}{path}"

    def _platform_url(self, path: str) -> str:
        # path here is the full /nexus/... relative path
        return f"{self._root}{path}"

    # ------------------------------------------------------------------ auth

    def login(self) -> None:
        """POST /login. Stores AuthCookie on the session, retains jwttoken,
        and (critically) sets X-Nd-Csrf-Token / X-Csrf-Token headers so any
        subsequent state-changing call (bootstrap/cluster, etc.) is accepted.

        Verified live on ND 4.2.1.10: response keys are
        {csrfToken, jwttoken, rbac, statusCode, token, username, usertype}."""
        url = self._root_url(ENDPOINTS["login"])
        body = {
            "userName": self.username,
            "userPasswd": self._password,
            "domain": self._domain,
        }
        try:
            r = self._session.post(url, json=body, verify=self._verify, timeout=self.timeout)
        except requests.RequestException as e:
            raise NdApiError(f"ND login network error to {self.host}: {e}") from e
        if r.status_code != 200:
            raise NdApiError(
                f"ND login failed for {self.host}: {r.status_code} {r.text[:300]}"
            )
        try:
            data = r.json()
        except ValueError:
            data = {}
        self._jwt = data.get("jwttoken") or data.get("token")
        csrf = data.get("csrfToken")
        if not self._jwt and "AuthCookie" not in self._session.cookies:
            raise NdApiError(
                f"ND login to {self.host} returned no jwttoken and no AuthCookie"
            )
        if csrf:
            self._session.headers["X-Nd-Csrf-Token"] = csrf
            self._session.headers["X-Csrf-Token"] = csrf
        log.info(
            "nd login ok",
            extra={
                "event": "nd.login",
                "node": self.host,
                "domain": self._domain,
                "cookieSet": "AuthCookie" in self._session.cookies,
                "csrfReceived": bool(csrf),
            },
        )

    def logout(self) -> None:
        """POST /logout. Best-effort; never raises."""
        if "AuthCookie" not in self._session.cookies and not self._jwt:
            return
        try:
            self._session.post(
                self._root_url(ENDPOINTS["logout"]),
                verify=self._verify,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            log.warning("nd logout network error", extra={
                "event": "nd.logout.err", "node": self.host, "err": str(e),
            })
        self._jwt = None
        self._session.headers.pop("X-Nd-Csrf-Token", None)
        self._session.headers.pop("X-Csrf-Token", None)
        self._session.cookies.clear()

    # ----------------------------------------------------------- bootstrap

    def bootstrap_status(self) -> dict[str, Any]:
        """GET /bootstrap/status -> {bootstrapped: bool, message: str}.

        This is the gate to decide whether to drive cluster bring-up via
        POST /bootstrap/cluster, or treat the cluster as already formed."""
        return self._request(
            "GET", self._root_url(ENDPOINTS["bootstrap_status"]),
        )

    def bootstrap_cluster_get(self) -> dict[str, Any]:
        """GET /bootstrap/cluster -> live template with the bootstrap node's
        identity already populated. Use this as the basis for the POST body."""
        return self._request(
            "GET", self._root_url(ENDPOINTS["bootstrap_cluster"]),
        )

    def bootstrap_cluster_submit(self, payload: dict[str, Any]) -> Any:
        """POST /bootstrap/cluster — triggers the actual cluster bring-up.

        WARNING: this is the one-shot, non-idempotent call that takes the
        single-node bootstrap appliance and turns it into a real 3-node
        cluster. Caller must verify with bootstrap_status() first. The body
        must follow the schema returned by bootstrap_cluster_get(): a
        complete {schemaversion, nodes[3], clusterConfig, cloudConfig} doc."""
        log.info(
            "nd bootstrap submit",
            extra={
                "event": "nd.bootstrap.submit",
                "node": self.host,
                "nodeCount": len((payload or {}).get("nodes") or []),
                "clusterName": (payload or {}).get("clusterConfig", {}).get("name"),
                "schemaversion": (payload or {}).get("schemaversion"),
            },
        )
        return self._request(
            "POST", self._root_url(ENDPOINTS["bootstrap_cluster"]),
            json=payload,
        )

    def wait_for_bootstrapped(
        self, *, timeout_s: int = 3600, poll_s: int = 30,
    ) -> dict[str, Any]:
        """Poll /bootstrap/status until bootstrapped=true."""
        deadline = time.time() + timeout_s
        last: dict[str, Any] = {}
        while time.time() < deadline:
            try:
                last = self.bootstrap_status()
            except NdApiError as e:
                log.warning(
                    "nd bootstrap poll error",
                    extra={"event": "nd.bootstrap.poll.err", "err": str(e)},
                )
                time.sleep(poll_s)
                continue
            done = bool(last.get("bootstrapped"))
            log.info(
                "nd bootstrap poll",
                extra={
                    "event": "nd.bootstrap.poll",
                    "bootstrapped": done,
                    "message": last.get("message"),
                },
            )
            if done:
                return last
            time.sleep(poll_s)
        raise NdApiError(
            f"cluster did not become bootstrapped within {timeout_s}s; last={last!r}"
        )

    # ------------------------------------------------------------------ HTTP

    @retry(
        retry=retry_if_exception_type((NdApiTransient, requests.RequestException)),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
        expect_json: bool = True,
    ) -> Any:
        r = self._session.request(
            method,
            url,
            json=json,
            params=params,
            verify=self._verify,
            timeout=self.timeout,
        )
        # Retry on rate-limit and 5xx (subagent A: 429 documented; no Retry-After).
        if r.status_code == 429 or 500 <= r.status_code < 600:
            raise NdApiTransient(
                f"{method} {url} -> {r.status_code} (retryable) {r.text[:200]}"
            )
        if r.status_code >= 400:
            raise NdApiError(f"{method} {url} -> {r.status_code} {r.text[:500]}")
        if not expect_json:
            return r
        if not r.content:
            return {}
        try:
            return r.json()
        except ValueError:
            # Per OpenAPI, createNode 200 response schema is `string` (example
            # text reads "NTP configuration updated successfully"). Return the
            # raw text wrapped so callers can introspect.
            return {"_raw": r.text}

    # ----------------------------------------------------------- discovery

    def is_reachable(self) -> bool:
        """True if the ND mgmt IP responds with anything <500. Used to gate
        the entire cluster_bringup phase on nd-1 being on the network."""
        try:
            r = self._session.get(
                f"https://{self.host}/", verify=self._verify, timeout=self.timeout,
            )
            return r.status_code < 500
        except requests.RequestException:
            return False

    def wait_for_reachable(self, timeout_s: int = 1800, poll_s: int = 15) -> None:
        deadline = time.time() + timeout_s
        last_err: str = "no attempt"
        while time.time() < deadline:
            if self.is_reachable():
                log.info("nd reachable", extra={"event": "nd.reachable", "node": self.host})
                return
            time.sleep(poll_s)
            last_err = "no <500 response"
        raise NdApiError(f"ND {self.host} not reachable within {timeout_s}s: {last_err}")

    # ----------------------------------------------------------- cluster

    def cluster_status(self, cluster_name: str | None = None) -> dict[str, Any]:
        """GET /api/v1/infra/cluster/status. Returns the live cluster doc:
        `state`, `status`, `nodeDetailsList[]`, `externalServiceStatusList[]`."""
        params = {"clusterName": cluster_name} if cluster_name else None
        return self._request(
            "GET", self._infra_url(ENDPOINTS["cluster_status"]), params=params,
        )

    def list_nodes(
        self, *, name: str | None = None, cluster_name: str | None = None,
    ) -> list[dict[str, Any]]:
        """GET /api/v1/infra/cluster/nodes [?nodeName=...]. Returns the raw list."""
        params: dict[str, Any] = {}
        if name:
            params["nodeName"] = name
        if cluster_name:
            params["clusterName"] = cluster_name
        body = self._request(
            "GET", self._infra_url(ENDPOINTS["cluster_nodes"]),
            params=params or None,
        )
        # TODO ASSUMED: list endpoint returns either a bare list or an envelope
        # like {"items":[...]} -- spec didn't make this explicit. Handle both.
        if isinstance(body, list):
            return body
        if isinstance(body, dict):
            for k in ("items", "nodes", "nodeList", "data"):
                if isinstance(body.get(k), list):
                    return body[k]
        return []

    def get_node(self, name: str) -> dict[str, Any] | None:
        for n in self.list_nodes(name=name):
            if (n.get("name") or n.get("hostname")) == name:
                return n
        return None

    def create_node(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /api/v1/infra/cluster/nodes. Adds one node per call (per
        OpenAPI: request body is a single nodeBootstrapConfig)."""
        log.info(
            "nd add node submit",
            extra={
                "event": "nd.node.create.submit",
                "node": self.host,
                "newNodeName": payload.get("name"),
                "role": payload.get("role"),
            },
        )
        return self._request(
            "POST",
            self._infra_url(ENDPOINTS["cluster_nodes"]),
            json=payload,
        )

    def wait_for_node_active(
        self, name: str, *, timeout_s: int = 3600, poll_s: int = 30,
    ) -> dict[str, Any]:
        """Poll list_nodes(name=...) until operationalState == active (or
        equivalent). Returns the final node doc."""
        deadline = time.time() + timeout_s
        last: dict[str, Any] | None = None
        while time.time() < deadline:
            try:
                last = self.get_node(name)
            except NdApiError as e:
                log.warning(
                    "nd node poll error",
                    extra={
                        "event": "nd.node.poll.err",
                        "node": self.host, "newNodeName": name, "err": str(e),
                    },
                )
                time.sleep(poll_s)
                continue
            if last is None:
                log.info(
                    "nd node not yet visible",
                    extra={"event": "nd.node.poll", "newNodeName": name},
                )
            else:
                op_state = (last.get("operationalState") or "").lower()
                bs_state = (last.get("bootstrapState") or "").lower()
                log.info(
                    "nd node poll",
                    extra={
                        "event": "nd.node.poll",
                        "newNodeName": name,
                        "operationalState": op_state,
                        "bootstrapState": bs_state,
                    },
                )
                if op_state in {"active", "ready", "operational"}:
                    return last
            time.sleep(poll_s)
        raise NdApiError(
            f"node {name!r} did not reach active within {timeout_s}s; last={last!r}"
        )

    def wait_for_cluster_active(
        self,
        *,
        expected_nodes: int = 3,
        timeout_s: int = 3600,
        poll_s: int = 30,
    ) -> dict[str, Any]:
        """Poll cluster_status until state is active and at least
        `expected_nodes` nodes show as active in nodeDetailsList."""
        deadline = time.time() + timeout_s
        last: dict[str, Any] = {}
        while time.time() < deadline:
            try:
                last = self.cluster_status()
            except NdApiError as e:
                log.warning(
                    "nd cluster status poll error",
                    extra={"event": "nd.cluster.poll.err", "err": str(e)},
                )
                time.sleep(poll_s)
                continue
            state = str(last.get("state") or "").lower()
            nodes = cluster_nodes(last)
            active = sum(
                1 for n in nodes
                if node_operational_state(n).lower()
                in {"active", "ready", "operational"}
            )
            log.info(
                "nd cluster poll",
                extra={
                    "event": "nd.cluster.poll",
                    "state": state,
                    "nodesActive": active,
                    "nodesExpected": expected_nodes,
                },
            )
            if state == "active" and active >= expected_nodes:
                return last
            time.sleep(poll_s)
        raise NdApiError(
            f"cluster did not reach active within {timeout_s}s; last_state={last.get('state')!r}"
        )

    # -------------------------------------------------- platform: cluster spec

    def platform_get_cluster(self, spec_name: str) -> dict[str, Any]:
        """GET /nexus/infra/api/platform/v1/clusters/{specName}."""
        return self._request(
            "GET", self._platform_url(f"{ENDPOINTS['platform_cluster']}/{spec_name}"),
        )

    def platform_put_cluster(self, spec_name: str, body: dict[str, Any]) -> Any:
        """PUT /nexus/infra/api/platform/v1/clusters/{specName}.

        TODO ASSUMED: PUT semantics (full replace vs partial merge) need
        live verification; per subagent A the docs don't make this explicit.
        Best practice: GET the doc, mutate fields, PUT it back whole.
        """
        return self._request(
            "PUT",
            self._platform_url(f"{ENDPOINTS['platform_cluster']}/{spec_name}"),
            json=body,
        )

    # ------------------------------------------------ platform: external IPs

    def platform_list_external_ips(self) -> Any:
        return self._request("GET", self._platform_url(ENDPOINTS["platform_externalips"]))

    def platform_create_external_ip_pool(
        self, *, name: str, ips: list[str], target_network: str = "Data",
    ) -> Any:
        """POST /nexus/infra/api/platform/v1/externalips. Creates the persistent
        IP pool we use for service IPs."""
        body = {
            "spec": {
                "name": name,
                "ip": list(ips),
                "targetNetwork": target_network,  # "Data" | "Management"
            }
        }
        log.info(
            "nd persistent ip pool create",
            extra={
                "event": "nd.externalip.create",
                "poolName": name,
                "count": len(ips),
                "targetNetwork": target_network,
            },
        )
        return self._request(
            "POST",
            self._platform_url(ENDPOINTS["platform_externalips"]),
            json=body,
        )


# ----------------------------------------------------------- payload builders

def build_node_payload(node: NodePayload) -> dict[str, Any]:
    """Map a NodePayload to the JSON schema accepted by POST /cluster/nodes
    in ND Infra v1 (createNode). Verified field-by-field against the OpenAPI
    nodeBootstrapConfig schema on Cisco DevNet."""
    if not node.cimc_ip or not node.cimc_user or not node.cimc_pass:
        raise ValueError(
            f"node {node.hostname!r}: cimc_ip/user/pass required for createNode"
        )
    if node.role not in {"primary", "secondary", "standby"}:
        raise ValueError(
            f"node {node.hostname!r}: role must be primary|secondary|standby, "
            f"got {node.role!r}"
        )
    body: dict[str, Any] = {
        "name": node.hostname,
        "role": node.role,
        "managementNetwork": {
            "network": {"cidrv4": f"{node.mgmt_ip}/{node.mgmt_mask}"},
            "gateway": {"ipv4": node.mgmt_gw},
        },
        "dataNetwork": {
            "network": {"cidrv4": f"{node.data_ip}/{node.data_mask}"},
            "gateway": {"ipv4": node.data_gw},
        },
        "nodeController": {
            "serverAddress": node.cimc_ip,
            "authentication": {
                "user": node.cimc_user,
                "password": node.cimc_pass,
            },
        },
    }
    if node.data_vlan is not None:
        if not 2 <= int(node.data_vlan) <= 4094:
            raise ValueError(
                f"node {node.hostname!r}: data_vlan must be 2..4094, "
                f"got {node.data_vlan!r}"
            )
        body["dataNetwork"]["vlanId"] = int(node.data_vlan)
    return body


def build_platform_cluster_patch(
    *,
    current_spec: dict[str, Any],
    cfg: ClusterSpec,
) -> dict[str, Any]:
    """Take the cluster doc returned by GET /platform/v1/clusters/{specName}
    and produce a PUT body with our DNS/NTP/proxy fields applied. Other
    fields (serviceNetwork, appNetwork, etc.) are passed through unchanged.

    TODO ASSUMED: exact field names below match subagent A's reading of the
    schema (`nameServers`, `ntpServers`, `proxyConfig`). Confirm with
    `verify_endpoints.py` which dumps the live cluster doc.
    """
    spec = dict((current_spec or {}).get("spec") or {})
    spec["nameServers"] = list(cfg.dns_servers)
    spec["ntpServers"] = list(cfg.ntp_servers)
    if cfg.proxy_skip:
        spec["proxyConfig"] = {
            "servers": [],
            "ignoreHosts": [],
            "username": "",
            "password": "",
        }
    else:
        spec["proxyConfig"] = {
            "servers": [cfg.proxy_url] if cfg.proxy_url else [],
            "ignoreHosts": list(cfg.proxy_ignore_hosts),
            "username": "",
            "password": "",
        }
    # TODO ASSUMED: timezone field name on the platform cluster spec is not
    # documented in the pages we retrieved. We attach it under a `timezone`
    # key as a best guess; verify_endpoints.py will report whether the live
    # spec accepts it (likely needs to be set via a different API or via
    # `timedatectl` on the node).
    spec["timezone"] = cfg.timezone
    out = dict(current_spec or {})
    out["spec"] = spec
    return out
