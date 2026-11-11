import argparse
import importlib
import json
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest
import yaml
from dotmap import DotMap


original_path = sys.path[:]
try:
    module = importlib.import_module(
        "roles.intersight_ucs_provision.library.src.intersight.configure"
    )
    sys.path.insert(0, str(Path(module.__file__).resolve().parents[2]))
    initialize = importlib.import_module(
        "roles.intersight_ucs_provision.library.src.initialize"
    )
    shared_functions = importlib.import_module(
        "roles.intersight_ucs_provision.library.src.shared_functions"
    )
finally:
    sys.path[:] = original_path


def configuration(check):
    return DotMap({
        "args": {"check": check},
        "org": "AIPOD-AB_ORG",
        "orgs": ["AIPOD-AB_ORG"],
        "org_moids": {"AIPOD-AB_ORG": {"moid": "org-moid"}},
        "imm_dict": {"orgs": {"AIPOD-AB_ORG": {"policies": {"imc_access": [{
            "name": "Access",
            "inband_ip_pool": "Inband",
            "out_of_band_ip_pool": "OoBand",
        }]}}}},
        "intersight_api": {},
        "ezdata": {
            "intersight.policies.imc_access": {
                "x-intersight-uri": "access/Policies",
            },
            "intersight.pools.ip": {
                "x-intersight-uri": "ippool/Pools",
            },
        },
    })


@pytest.mark.parametrize("existing", [(), ("Inband",), ("Inband", "OoBand")])
@pytest.mark.parametrize("check", [True, False])
def test_missing_pool_dependencies(monkeypatch, capsys, check, existing):
    kwargs = configuration(check)
    calls = []

    def api_calls(_self, state):
        calls.append((state.method, state.uri, list(state.names)))
        state.results = []
        if state.uri == "ippool/Pools":
            for name in existing:
                state.intersight_api[state.org].pools.ip[name] = DotMap(
                    moid=f"{name}-moid"
                )
                state.results.append({"Name": name, "Moid": f"{name}-moid"})
        return state

    monkeypatch.setattr(module.api, "calls", api_calls)
    monkeypatch.setattr(
        module.configure, "name_prefix_suffix", lambda *_args: ("", "")
    )
    render = Mock(return_value={"Name": "Access"})
    compare = Mock(side_effect=lambda _body, _title, state: state)
    monkeypatch.setattr(module.configure, "create_api_body", render)
    monkeypatch.setattr(module.configure, "compare_resources_to_api", compare)
    provision = module.configure(category="policies", type="imc_access")

    if not check and not existing:
        with pytest.raises(ValueError, match="Empty API query results for ippool/Pools"):
            provision.configure(kwargs)
        render.assert_not_called()
    else:
        result = provision.configure(kwargs)
        assert result.org == "AIPOD-AB_ORG"
        output = capsys.readouterr().out
        if check and len(existing) < 2:
            render.assert_not_called()
            assert "deferred payload validation" in output
            assert "pools/ip: AIPOD-AB_ORG/OoBand" in output
            assert "No payloads for this resource type were validated or submitted" in " ".join(output.split())
        else:
            render.assert_called_once()
            compare.assert_called_once()
            assert "deferred payload validation" not in output
    assert [uri for _, uri, _ in calls] == ["access/Policies", "ippool/Pools"]
    assert all(method == "get" for method, _, _ in calls)


def test_dependency_api_errors_propagate_in_check_mode(monkeypatch):
    kwargs = configuration(check=True)

    def api_calls(_self, state):
        if state.uri == "ippool/Pools":
            raise RuntimeError("API request failed")
        state.results = []
        return state

    monkeypatch.setattr(module.api, "calls", api_calls)
    monkeypatch.setattr(
        module.configure, "name_prefix_suffix", lambda *_args: ("", "")
    )
    with pytest.raises(RuntimeError, match="API request failed"):
        module.configure(category="policies", type="imc_access").configure(kwargs)


def test_vlan_multicast_references_use_policy_name_decoration():
    kwargs = configuration(check=True)
    org = kwargs.org
    kwargs.imm_dict.orgs[org].policies.name_prefix.default = "AIPOD-AID-"
    kwargs.imm_dict.orgs[org].policies.name_suffix.default = "-Policy"
    kwargs.intersight_api[org].policies.multicast = DotMap()
    kwargs.cp = DotMap()
    item = DotMap({
        "name": "VLAN",
        "vlans": [
            {"name": "Management", "multicast_policy": "Multicast"},
            {"name": "Storage", "multicast_policy": "Multicast"},
        ],
    })

    item, state = module.configure(category="policies", type="vlan").existing_check(
        item, kwargs
    )

    assert [vlan.multicast_policy for vlan in item.vlans] == [
        f"{org}/AIPOD-AID-Multicast-Policy",
        f"{org}/AIPOD-AID-Multicast-Policy",
    ]
    assert state.cp.multicast.category == "policies"
    assert state.cp.multicast.names == [
        f"{org}/AIPOD-AID-Multicast-Policy",
    ]


def test_empty_pool_lookup_plans_creation_in_check_mode(monkeypatch, capsys):
    kwargs = configuration(check=True)
    kwargs.imm_dict.orgs[kwargs.org].pools.ip = [
        DotMap(name="Inband"), DotMap(name="OoBand")
    ]

    def api_calls(_self, state):
        assert state.method == "get"
        assert state.uri == "ippool/Pools"
        state.results = []
        return state

    monkeypatch.setattr(module.api, "calls", api_calls)
    monkeypatch.setattr(
        module.configure, "name_prefix_suffix", lambda *_args: ("", "")
    )
    monkeypatch.setattr(
        module.configure, "create_api_body",
        lambda _self, item, _np, _ns, _state: {"Name": item.name},
    )
    result = module.configure(category="pools", type="ip").configure(kwargs)
    output = " ".join(capsys.readouterr().out.split())
    assert "would create new Pools -> IP: `Inband`" in output
    assert "would create new Pools -> IP: `OoBand`" in output
    assert result.bulk_list == []


def test_cross_org_dependency_is_deferred_without_changing_active_org(monkeypatch, capsys):
    kwargs = configuration(check=True)
    item = kwargs.imm_dict.orgs[kwargs.org].policies.imc_access[0]
    item.inband_ip_pool = "Shared/Inband"
    item.out_of_band_ip_pool = "Shared/OoBand"
    kwargs.org_moids.Shared.moid = "shared-org-moid"

    def api_calls(_self, state):
        state.results = []
        return state

    monkeypatch.setattr(module.api, "calls", api_calls)
    monkeypatch.setattr(
        module.configure, "name_prefix_suffix", lambda *_args: ("", "")
    )
    render = Mock()
    monkeypatch.setattr(module.configure, "create_api_body", render)
    result = module.configure(category="policies", type="imc_access").configure(kwargs)
    assert result.org == "AIPOD-AB_ORG"
    assert "pools/ip: Shared/OoBand" in " ".join(capsys.readouterr().out.split())
    render.assert_not_called()


@pytest.mark.parametrize("platform", ["UCS Domain", "Unified Edge"])
@pytest.mark.parametrize("tags", [
    [],
    [{"key": "Environment", "value": "Test"}],
    [{"key": "Location/Lab", "tag_type": "PathTag"}],
])
@pytest.mark.parametrize("watchdog", [
    {},
    {"watchdog_enabled": False, "shutdown_multiplier": 3, "watchdog_interval": 1000},
])
def test_system_qos_payload(platform, tags, watchdog):
    kwargs = configuration(check=True)
    kwargs.script_path = str(
        Path(module.__file__).resolve().parents[2]
    )
    item = DotMap({
        "name": "QoS",
        "target_platform": platform,
        "classes": [{"priority": "Gold", "state": "Enabled", "weight": 10}],
        "tags": tags,
        "priority_flow_control_watchdog_configuration": watchdog,
    })
    payload = module.configure(category="policies", type="system_qos").create_api_body(
        item, "", "", kwargs
    )

    assert payload["Name"] == "QoS"
    assert payload["TargetPlatform"] == platform
    assert payload["Organization"]["Moid"] == "org-moid"
    assert payload["Classes"][0]["Name"] == "Gold"
    assert payload["Classes"][0]["Mtu"] == 1500
    assert payload["Tags"] == [
        {"Key": tag["key"], "Type": tag.get("tag_type", "KeyValue"),
         **({"Value": tag["value"]} if "value" in tag else {})}
        for tag in tags
    ]
    expected = {
        "IsWatchdogEnabled": True,
        "ObjectType": "fabric.PfcWatchDog",
        "ShutdownMultiplier": 1,
        "WatchdogInterval": 500,
    }
    if platform == "Unified Edge":
        expected["IsWatchdogEnabled"] = False
    elif watchdog:
        expected.update(
            IsWatchdogEnabled=False, ShutdownMultiplier=3, WatchdogInterval=1000
        )
    assert payload["PfcWatchdog"] == expected


@pytest.mark.parametrize("expression,expected", [
    ("101,102", [101, 102]),
    ("101-102", [101, 102]),
    ("101,4043-4047,4094,102", [101, 102]),
    ("4043-4047,4094", []),
])
def test_vlan_children_skip_reserved_ids_without_parsing_internal_list(
        monkeypatch, capsys, expression, expected):
    kwargs = configuration(check=True)
    kwargs.resources = [DotMap({
        "name": "Vlans",
        "vlans": [{"name": "vlan_", "vlan_list": expression}],
    })]
    kwargs.intersight_api[kwargs.org].policies.vlan.Vlans.moid = "vlan-policy-moid"
    monkeypatch.setattr(
        module.configure, "children_check_parent",
        lambda _self, _child_type, state: (1, state),
    )
    monkeypatch.setattr(
        module.configure, "name_prefix_suffix", lambda *_args: ("", "")
    )
    bodies = []

    def render(_self, item, _np, _ns, _state):
        body = {"Name": item.name, "VlanId": item.vlan_id, "Parent": item.parent}
        bodies.append(body)
        return body

    monkeypatch.setattr(module.configure, "create_api_body", render)
    monkeypatch.setattr(
        module.configure, "children_compare_api_body",
        lambda _self, _body, state: state,
    )
    module.configure(category="policies", type="vlan").policies_vlan_vlans(kwargs)
    assert [body["VlanId"] for body in bodies] == expected
    assert all(body["Parent"] == "vlan-policy-moid" for body in bodies)
    assert all(body["Name"] == f"vlan_{body['VlanId']}" for body in bodies)
    if "4043" in expression:
        assert "reserved VLAN" in capsys.readouterr().out


@pytest.mark.parametrize("expression", ["0", "4095", "4096", "102-101", "invalid"])
def test_invalid_user_vlan_ids_remain_rejected(expression):
    with pytest.raises(ValueError):
        module.shared_functions.vlan_list_full(expression)


@pytest.mark.parametrize("category", ["templates", "profiles"])
@pytest.mark.parametrize("attached", [False, True])
@pytest.mark.parametrize("resource_type,platform", [
    ("domain", "UCS Domain"), ("unified_edge", "Unified Edge"),
])
def test_domain_orchestration_renders_valid_target_platform(
        monkeypatch, category, attached, resource_type, platform):
    kwargs = configuration(check=False)
    kwargs.script_path = str(Path(module.__file__).resolve().parents[2])
    kwargs.resources = [DotMap({"name": "XDirect", "target_platform": "Domain"})]
    if attached and category == "profiles":
        template_key = platform.lower().replace(" ", "_") + "_profile_template"
        kwargs.resources[0][template_key] = "Shared/Source"
        kwargs.resources[0].attach_template = True
        kwargs.intersight_api.Shared.templates.domain.Source = DotMap({
            "moid": "cluster-template-moid",
            "switch": {
                "Source-A": {"moid": "switch-template-a"},
                "Source-B": {"moid": "switch-template-b"},
            },
        })
        resolver = module.configure.resolve_domain_template

        def resolve_with_copied_state(self, reference, state):
            from copy import deepcopy
            cluster, switches, result = resolver(self, reference, state)
            return cluster, switches, deepcopy(result)

        monkeypatch.setattr(module.configure, "resolve_domain_template", resolve_with_copied_state)
    for kind, uri in (
        ("domain", "fabric/SwitchClusterProfile" + ("Templates" if category == "templates" else "s")),
        ("domain.switch", "fabric/SwitchProfile" + ("Templates" if category == "templates" else "s")),
    ):
        kwargs.ezdata[f"intersight.{category}.{kind}"] = {"x-intersight-uri": uri}
    monkeypatch.setattr(
        module.configure, "name_prefix_suffix", lambda *_args: ("", "")
    )
    monkeypatch.setattr(
        module.configure, "api_get",
        lambda _self, _empty, _names, _otype, state: state,
    )
    parents = []
    children = []
    requests = []

    def compare(_self, body, _title, state):
        parents.append(body)
        state.bulk_list.append(body)
        return state

    def submit(_self, state):
        requests.extend(state.bulk_list)
        state.intersight_api[state.org][category].domain.XDirect.moid = "parent-moid"
        return state

    def compare_child(_self, body, state):
        children.append(body)
        state.bulk_list.append(body)
        return state

    monkeypatch.setattr(module.configure, "compare_resources_to_api", compare)
    monkeypatch.setattr(module.configure, "create_bulk_request", submit)
    monkeypatch.setattr(module.configure, "children_compare_api_body", compare_child)
    def attach(state):
        assert len(requests) == 3
        return state

    attachment = Mock(side_effect=attach)
    monkeypatch.setattr(module.configure, "profiles_domain_attach_templates", attachment)
    def deploy(_profiles, state):
        assert attachment.call_count == 1
        assert len(requests) == 3
        return state

    deployment = Mock(side_effect=deploy)
    monkeypatch.setattr(module.configure, "profiles_domain_deploy", deployment)
    provision = module.configure(category=category, type=resource_type)
    result = getattr(provision, f"{category}_{resource_type}")(kwargs)

    assert len(parents) == 1
    assert parents[0]["TargetPlatform"] == platform
    assert parents[0]["ObjectType"] == (
        "fabric.SwitchClusterProfileTemplate" if category == "templates" else "fabric.SwitchClusterProfile"
    )
    assert len(children) == 2
    assert [body["SwitchId"] for body in children] == ["A", "B"]
    assert all(body["Parent"]["Moid"] == "parent-moid" for body in children)
    assert len(requests) == 3
    assert result.resources[0].target_platform == platform
    assert attachment.call_count == (1 if category == "profiles" else 0)
    assert deployment.call_count == (1 if category == "profiles" else 0)
    if attached and category == "profiles":
        assert parents[0]["SrcTemplate"]["Moid"] == "cluster-template-moid"
        assert [body["SrcTemplate"]["Moid"] for body in children] == [
            "switch-template-a", "switch-template-b",
        ]
        assert "DotMap()" not in str(requests)


@pytest.mark.parametrize("resource_type", ["domain", "chassis", "server", "unified_edge"])
@pytest.mark.parametrize("check", [False, True])
@pytest.mark.parametrize("found", [[], ["FDO29100001"], ["FDO29100001", "FDO29100002"]])
def test_profile_serial_lookups_require_every_requested_serial(
        monkeypatch, resource_type, check, found, capsys):
    kwargs = configuration(check=check)
    serials = ["FDO29100001", "FDO29100002"]
    if resource_type == "domain":
        kwargs.resources = [DotMap({"name": "Domain", "serial_numbers": serials})]
    else:
        kwargs.resources = [DotMap({"name": f"Profile-{index}", "serial_number": serial})
                            for index, serial in enumerate(serials)]
    kwargs.ezdata[f"intersight.profiles.{resource_type}"] = {
        "x-intersight-uri-serial": "test/Hardware",
        "x-intersight-object-type": "test.Profile",
    }
    monkeypatch.setattr(module.configure, "name_prefix_suffix", lambda *_args: ("", ""))

    def lookup(state):
        state.results = [DotMap({"Serial": serial, "Moid": f"moid-{serial}"}) for serial in found]
        state.uri = "test/Hardware"
        return state

    def api_calls(_self, state):
        assert list(state.names) == serials
        return lookup(state)

    def system_lookup(_empty, names, state):
        assert names == serials
        state.org = "default"
        return lookup(state)

    monkeypatch.setattr(module.api, "calls", api_calls)
    monkeypatch.setattr(module, "system", lambda **_kwargs: Mock(api_get=system_lookup))
    provision = module.configure(category="profiles", type=resource_type)
    downstream = Mock(side_effect=RuntimeError("downstream reached"))
    monkeypatch.setattr(module.configure, "api_get", downstream)
    monkeypatch.setattr(module.configure, "profiles_org_map", downstream)
    action = (provision.profiles_templates_domain_unified_edge
              if resource_type in ("domain", "unified_edge") else provision.profiles_chassis_server)

    if len(found) == 2:
        with pytest.raises(RuntimeError, match="downstream reached"):
            action(kwargs)
    else:
        with pytest.raises(ValueError, match="serial number\\(s\\) not found in Intersight") as error:
            action(kwargs)
        assert "FDO29100002" in str(error.value)
        assert ("FDO29100001" in str(error.value)) == (not found)
        assert "AIPOD-AB_ORG" in str(error.value)
        assert "test/Hardware" in str(error.value)
        assert "!!! ERROR !!!" in " ".join(capsys.readouterr().out.split())
        downstream.assert_not_called()
    assert kwargs.org == "AIPOD-AB_ORG"


def test_serial_validation_does_not_accept_stale_cache_or_missing_moid():
    kwargs = configuration(check=True)
    serial = "FDO29100001"
    kwargs.intersight_api.system.serial_number[serial].moid = "cached-moid"
    kwargs.results = [DotMap({"Serial": serial})]
    kwargs.uri = "compute/PhysicalSummaries"
    with pytest.raises(ValueError, match=serial):
        module.configure(category="profiles", type="server").validate_serial_results([serial], kwargs)


@pytest.mark.parametrize("check", [False, True])
@pytest.mark.parametrize("profile_types", [
    ["server", "chassis", "domain"],
    ["chassis", "domain", "server"],
    ["server", "chassis", "unified_edge", "domain"],
    ["server", "chassis"],
    ["domain"],
])
def test_profile_deployment_dependency_order(monkeypatch, check, profile_types):
    kwargs = DotMap({
        "args": {"check": check},
        "imm_dict": {"orgs": {
            org: {
                "profiles": {ptype: [] for ptype in profile_types},
                "pools": {"ip": []},
                "policies": {"ntp": []},
                "templates": {"server": []},
            } for org in ["Org-A", "Org-B"]
        }},
        "ezdata": {
            **{f"intersight.profiles.{ptype}": {"x-intersight-object-type": "test.Profile"}
               for ptype in [*profile_types, "switch"]},
            "intersight.pools.ip": {"x-intersight-object-type": "ippool.Pool"},
            "intersight.policies.ntp": {"x-intersight-object-type": "ntp.Policy"},
            "intersight.templates.server": {"x-intersight-object-type": "server.ProfileTemplate"},
        },
    })
    monkeypatch.setattr(initialize.api, "all_organizations", lambda _self, state: state)
    calls = []

    def configure_resource(category, type):
        def run(state):
            calls.append((category, type, state.org))
            return state
        return Mock(configure=run)

    monkeypatch.setattr(initialize, "configure", configure_resource)
    result = initialize.begin(type="deployment").functions_to_run(kwargs)
    expected_order = [ptype for ptype in ["domain", "unified_edge", "chassis", "server"]
                      if ptype in profile_types]
    assert result.profiles_list == expected_order
    assert calls == [
        (category, ptype, org)
        for category, ptype in [
            ("pools", "ip"), ("policies", "ntp"), ("templates", "server"),
            *(("profiles", ptype) for ptype in expected_order),
        ]
        for org in ["Org-A", "Org-B"]
    ]


@pytest.mark.parametrize("check", [False, True])
def test_system_only_yaml_deploys_without_org_scoped_configuration(monkeypatch, tmp_path, check):
    payload = {"intersight": {"system": {
        "organizations": [{"name": "AIPOD-AB_RG", "resource_groups": ["AIPOD-AB_RG"]}],
        "resource_groups": [{"name": "AIPOD-AB_RG", "description": "AI POD in RTP B4 - Row AB",
                             "resources": {"targets": ["AB07-UCSX-AID-1"]}}],
    }}}
    (tmp_path / "system.ezai.yaml").write_text(yaml.safe_dump(payload))
    library = Path(initialize.__file__).resolve().parents[1]
    kwargs = DotMap({
        "args": {"dir": str(tmp_path), "check": check},
        "script_path": str(library),
        "schema_path": str(library.parents[2] / "schema"),
        "imm_dict": {"orgs": {}},
        "ezdata": {
            "intersight.system.organizations": {"x-intersight-object-type": "organization.Organization"},
            "intersight.system.resource_groups": {"x-intersight-object-type": "resource.Group"},
        },
    })
    kwargs = shared_functions.load_configurations(kwargs)
    calls = []

    def discover(_self, state):
        calls.append("discover")
        return state

    def system_resource(category, type):
        def run(state):
            calls.append((category, type))
            return state
        return Mock(system=run)

    monkeypatch.setattr(initialize.api, "all_organizations", discover)
    monkeypatch.setattr(initialize, "system", system_resource)
    configure_resource = Mock()
    monkeypatch.setattr(initialize, "configure", configure_resource)
    result = initialize.begin(type="deployment").functions_to_run(kwargs)
    assert result.orgs == []
    assert result.imm_dict.system.toDict() == payload["intersight"]["system"]
    assert calls == ["discover", ("system", "resource_groups"), ("system", "organizations")]
    configure_resource.assert_not_called()


def test_empty_configuration_is_rejected_before_api_calls(monkeypatch):
    discover = Mock()
    monkeypatch.setattr(initialize.api, "all_organizations", discover)
    with pytest.raises(ValueError, match="No organizations"):
        initialize.begin(type="deployment").functions_to_run(DotMap(imm_dict={"orgs": {}}))
    discover.assert_not_called()


@pytest.mark.parametrize("release", ["v0.1.5", "v9.8.7"])
def test_automatic_tags_use_running_release_not_schema_version(monkeypatch, tmp_path, release):
    (tmp_path / "VERSION").write_text(release + "\n")
    schema_dir = tmp_path / "schema"
    schema_dir.mkdir()
    (schema_dir / "cisco-ai-pods.json").write_text(json.dumps({
        "$ref": "#/definitions/intersight",
        "definitions": {"intersight": {"type": "object"}},
        "x-schema-version": "0.1.0",
    }))
    monkeypatch.setattr(shared_functions, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(shared_functions.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(shared_functions.pcolor, "init_log", lambda _path: None)
    monkeypatch.setattr(shared_functions.logging, "basicConfig", lambda **_kwargs: None)
    monkeypatch.setattr(sys, "argv", ["/test/deploy_intersight_ucs.py"])
    args = argparse.Namespace(dir=str(tmp_path), intersight_secret_key=None, intersight_fqdn=None)
    result = shared_functions.base_script_settings(DotMap(args=args))
    assert result.ez_tags == [
        {"key": "managed-by", "value": "cisco-ai-pods"},
        {"key": "release", "value": release},
    ]
    for enabled in [True, False]:
        result.intersight.global_settings.include_script_tags = enabled
        item = module.configure(type="ntp").merge_tags(
            DotMap(tags=[{"key": "site", "value": "RTP"}]), result)
        assert item.tags == [{"key": "site", "value": "RTP"}] + (result.ez_tags if enabled else [])


@pytest.mark.parametrize("release", ["v0.1.5", "v9.8.7"])
def test_bundled_schema_version_follows_version_file(monkeypatch, tmp_path, release):
    monkeypatch.syspath_prepend(str(Path(module.__file__).resolve().parents[5] / "scripts"))
    bundler = importlib.import_module("merge_schemas")
    version = tmp_path / "VERSION"
    version.write_text(release + "\n")
    monkeypatch.setattr(bundler, "VERSION_FILE", version)
    documents = bundler.load_sources(Path(module.__file__).resolve().parents[5] / "schemas" / "source")
    documents[bundler.ROOT_FILE]["x-schema-version"] = "stale"
    bundle = bundler.build_bundle(documents)
    assert bundle["x-schema-version"] == release


@pytest.mark.parametrize("reference", ["XDirect", "Shared/XDirect"])
@pytest.mark.parametrize("missing", [None, "cluster", "A", "B"])
def test_domain_template_resolution_queries_real_cache_shape(
        monkeypatch, reference, missing):
    kwargs = configuration(check=False)
    org = "Shared" if "/" in reference else kwargs.org
    kwargs.org_moids[org].moid = "template-org-moid"
    kwargs.ezdata["intersight.templates.domain"] = {
        "x-intersight-uri": "fabric/SwitchClusterProfileTemplates",
    }
    kwargs.ezdata["intersight.templates.domain.switch"] = {
        "x-intersight-uri": "fabric/SwitchProfileTemplates",
    }
    kwargs.intersight_object_map = {
        "fabric.SwitchClusterProfileTemplate": "domain",
        "fabric.SwitchProfileTemplate": "domain.switch",
    }
    # DotMap placeholders must not count as resolved templates.
    kwargs.intersight_api[org].templates.domain.XDirect.moid = DotMap()
    calls = []

    def api_calls(api_self, state):
        calls.append((api_self.type, state.org, list(state.names)))
        if api_self.type == "domain":
            results = [] if missing == "cluster" else [
                {"Name": "XDirect", "Moid": "cluster-id",
                 "ObjectType": "fabric.SwitchClusterProfileTemplate", "Tags": []},
            ]
        else:
            assert list(state.names) == ["cluster-id"]
            results = [
                {"Name": f"XDirect-{side}", "Moid": f"switch-{side}",
                 "ObjectType": "fabric.SwitchProfileTemplate",
                 "SwitchClusterProfileTemplate": {"Moid": "cluster-id"}}
                for side in ["A", "B"] if side != missing
            ]
        state.build_skip = False
        state = api_self.build_intersight_api_dict(DotMap({"Results": results}), state)
        state.results = [DotMap(result) for result in results]
        return state

    monkeypatch.setattr(module.api, "calls", api_calls)
    provision = module.configure(category="profiles", type="domain")
    if missing:
        with pytest.raises(ValueError, match="Unable to resolve domain profile template") as error:
            provision.resolve_domain_template(reference, kwargs)
        assert f"{org}/XDirect" in str(error.value)
        if missing != "cluster":
            assert f"XDirect-{missing}" in str(error.value)
    else:
        cluster, switches, state = provision.resolve_domain_template(reference, kwargs)
        assert cluster == "cluster-id"
        assert switches == {"A": "switch-A", "B": "switch-B"}
        assert state.org == "AIPOD-AB_ORG"
        assert calls == [("domain", org, ["XDirect"]), ("domain.switch", org, ["cluster-id"])]
        provision.resolve_domain_template(reference, state)
        assert len(calls) == 2


def test_template_query_errors_restore_organization(monkeypatch):
    kwargs = configuration(check=False)
    kwargs.intersight_api.Shared.templates.domain.XDirect.moid = "cluster-id"

    def fail(*_args):
        raise RuntimeError("API unavailable")

    monkeypatch.setattr(module.configure, "api_get", fail)
    with pytest.raises(RuntimeError, match="API unavailable"):
        module.configure(category="profiles", type="domain").resolve_domain_template(
            "Shared/XDirect", kwargs)
    assert kwargs.org == "AIPOD-AB_ORG"


@pytest.mark.parametrize("resource_type", ["domain", "unified_edge"])
@pytest.mark.parametrize("case", [
    "new", "reference-only", "attached", "delayed", "timeout",
    "check", "detached", "api-error", "missing-child",
])
def test_domain_template_binding_and_policy_inheritance(monkeypatch, resource_type, case, capsys):
    from copy import deepcopy

    kwargs = configuration(check=case == "check")
    key = ("ucs_domain_profile_template" if resource_type == "domain"
           else "unified_edge_profile_template")
    kwargs.resources = [DotMap({
        "name": "pre-Domain-post", key: "Shared/Source",
        "attach_template": case != "detached",
        "cluster_template_moid": "source-parent",
        "switch_template_moids": {"A": "source-A", "B": "source-B"},
    })]
    kwargs.intersight_api[kwargs.org].profiles.domain["pre-Domain-post"] = DotMap({
        "moid": "target-parent",
        "switch": {
            f"pre-Domain-post-{side}": {"moid": f"target-{side}"} for side in ["A", "B"]
        },
    })
    if case == "missing-child":
        del kwargs.intersight_api[kwargs.org].profiles.domain["pre-Domain-post"].switch["pre-Domain-post-B"]
    for category, suffix in [("templates", "Template"), ("profiles", "")]:
        for kind, object_type in [
            ("domain", f"fabric.SwitchClusterProfile{suffix}"),
            ("domain.switch", f"fabric.SwitchProfile{suffix}"),
        ]:
            kwargs.ezdata[f"intersight.{category}.{kind}"] = {
                "x-intersight-object-type": object_type,
                "x-intersight-uri": object_type.replace(".", "/") + "s",
            }
    qos = {"Moid": "qos-id", "ObjectType": "fabric.SystemQosPolicy"}
    merged = set()
    polls = {}
    requests = []

    def api_calls(self, state):
        requests.append((state.method, state.uri, deepcopy(state.get("api_body"))))
        if self.type == "bulk_merger":
            body = state.api_body
            target = body["Targets"][0]["Moid"]
            assert body["Sources"][0]["Moid"] == target.replace("target", "source")
            assert body["MergeAction"] == "Merge"
            assert body["Sources"][0]["ObjectType"].endswith("Template")
            assert not body["Targets"][0]["ObjectType"].endswith("Template")
            if case == "api-error":
                raise RuntimeError("merge API failed")
            merged.add(target)
        elif self.category == "templates":
            state.results = DotMap({"PolicyBucket": [qos] if self.type == "domain.switch" else []})
        else:
            target = state.pmoid
            policies = []
            bound = case in ("attached", "reference-only") or target in merged
            if target in merged:
                polls[target] = polls.get(target, 0) + 1
            ready = (case == "attached" or
                     (target in merged and case != "timeout"
                      and (case != "delayed" or polls[target] > 1)))
            if ready and self.type == "domain.switch":
                policies = [qos]
            state.results = DotMap({
                "SrcTemplate": {"Moid": target.replace("target", "source")} if bound else None,
                "PolicyBucket": policies,
            })
        # Real API helpers can replace the entire state.
        return deepcopy(state)

    monkeypatch.setattr(module.api, "calls", api_calls)
    sleeps = Mock()
    monkeypatch.setattr(module.time, "sleep", sleeps)
    provision = module.configure(category="profiles", type=resource_type)
    if case in ("timeout", "api-error", "missing-child"):
        error_type, message = {
            "timeout": (RuntimeError, "Deployment has not been submitted"),
            "api-error": (RuntimeError, "merge API failed"),
            "missing-child": (ValueError, "profile has no Moid"),
        }[case]
        with pytest.raises(error_type, match=message):
            provision.profiles_domain_attach_templates(kwargs)
    else:
        result = provision.profiles_domain_attach_templates(kwargs)
        assert result.org == kwargs.org
    if case in ("check", "detached"):
        assert requests == []
        if case == "check":
            assert "verify A/B policy inheritance" in " ".join(capsys.readouterr().out.split())
    elif case == "attached":
        assert merged == set()
    elif case == "reference-only":
        assert merged == {"target-A", "target-B"}
    elif case in ("new", "delayed"):
        assert merged == {"target-parent", "target-A", "target-B"}
    if case == "delayed":
        assert sleeps.call_count == 2
    assert not any(body and body.get("Action") == "Deploy" for _, _, body in requests)


@pytest.mark.parametrize("resource_type", ["domain", "unified_edge"])
@pytest.mark.parametrize("action", ["Deploy", "No-op"])
def test_domain_wrapper_runs_deployment_after_reconciliation(monkeypatch, resource_type, action):
    kwargs = configuration(check=False)
    kwargs.resources = [DotMap({"name": "Domain", "action": action})]
    events = []

    def reconcile(_self, state):
        events.append("reconcile")
        state.resources[0].name = "prefix-Domain"
        return state

    def deploy(_self, profiles, state):
        events.append("deploy")
        assert profiles[0].name == "Domain"
        assert profiles[0].action == action
        return state

    monkeypatch.setattr(module.configure, "profiles_templates_domain_unified_edge", reconcile)
    monkeypatch.setattr(module.configure, "profiles_domain_deploy", deploy)
    provision = module.configure(category="profiles", type=resource_type)
    getattr(provision, f"profiles_{resource_type}")(kwargs)
    assert events == ["reconcile", "deploy"]


@pytest.mark.parametrize("case", [
    "deploy", "check", "noop", "already", "missing-b", "unassigned", "failed", "timeout",
])
def test_domain_switch_deployment_requests_and_waiting(monkeypatch, case, capsys):
    kwargs = configuration(check=case == "check")
    kwargs.ezdata["intersight.profiles.domain.switch"] = {"x-intersight-uri": "fabric/SwitchProfiles"}
    kwargs.intersight_api[kwargs.org].profiles.domain["pre-Domain-post"].moid = "cluster-id"
    profiles = [DotMap({"name": "Domain", "action": "No-op" if case == "noop" else "Deploy"})]
    children = [
        DotMap({"Name": f"pre-Domain-post-{side}", "Moid": f"switch-{side}", "SwitchId": side,
                "AssignedSwitch": {"Moid": f"hardware-{side}"},
                "SwitchClusterProfile": {"Moid": "cluster-id"},
                "ConfigContext": {"ConfigState": "Assigned", "ControlAction": "No-op"},
                "ConfigChanges": {"Changes": []}})
        for side in ["A", "B"]
    ]
    if case == "missing-b":
        children.pop()
    if case == "unassigned":
        children[1].AssignedSwitch = None
    if case == "already":
        for child in children:
            child.ConfigContext.ConfigState = "Associated"
    lookups, payloads, polls = [], [], []

    def lookup(self, _empty, names, _otype, state):
        lookups.append((self.type, names))
        state.results = children if self.type == "domain.switch" else []
        return state

    def api_calls(self, state):
        if self.type == "bulk_request":
            payloads.extend(state.api_body["Requests"])
        else:
            polls.append(state.pmoid)
            state.results = DotMap({"ConfigContext": {
                "ControlAction": "No-op" if case != "timeout" else "Deploy",
                "ConfigState": "Failed" if case == "failed" else "Assigned" if case == "timeout" else "Associated",
            }})
        return state

    monkeypatch.setattr(module.configure, "name_prefix_suffix", lambda *_args: ("pre-", "-post"))
    monkeypatch.setattr(module.configure, "api_get", lookup)
    monkeypatch.setattr(module.api, "calls", api_calls)
    def sleep(seconds):
        assert seconds == 60
        output = " ".join(capsys.readouterr().out.split())
        assert "Deploying Changes for" in output
        assert "Sleeping for 60 Seconds" in output
        assert "deployment check" in output
        if not polls:
            assert "Beginning Profile Deployment for `pre-Domain-post-A`" in output
            assert "Beginning Profile Deployment for `pre-Domain-post-B`" in output
            assert "Completed deployment PATCH for Organization: `AIPOD-AB_ORG`" in output
            assert "Name: pre-Domain-post-A - Moid: switch-A" in output
            assert "Name: pre-Domain-post-B - Moid: switch-B" in output
            assert len(payloads) == 2

    monkeypatch.setattr(module.time, "sleep", sleep)
    provision = module.configure(category="profiles", type="domain")
    expected_error = {
        "missing-b": (ValueError, "fabric B"),
        "unassigned": (ValueError, "no assigned switch"),
        "failed": (RuntimeError, "deployment failed"),
        "timeout": (TimeoutError, "timed out"),
    }.get(case)
    if expected_error:
        with pytest.raises(expected_error[0], match=expected_error[1]):
            provision.profiles_domain_deploy(profiles, kwargs)
    else:
        provision.profiles_domain_deploy(profiles, kwargs)
    if case in ("deploy", "failed", "timeout"):
        assert len(payloads) == 2
        assert [payload["TargetMoid"] for payload in payloads] == ["switch-A", "switch-B"]
        assert all(payload["Verb"] == "PATCH" for payload in payloads)
        assert all(payload["Uri"] == "/v1/fabric/SwitchProfiles" for payload in payloads)
        assert all(payload["Body"]["Action"] == "Deploy" for payload in payloads)
        assert polls
        if case == "deploy":
            assert polls == ["switch-A", "switch-B"]
            assert "Completed Switch Profile Deployment for `pre-Domain-post-B`" in capsys.readouterr().out
        elif case == "timeout":
            assert len(polls) == 30
    else:
        assert payloads == []
        assert polls == []
        output = capsys.readouterr().out
        assert "Beginning Profile Deployment" not in output
        assert "Completed deployment PATCH" not in output
        assert "Sleeping for 60 Seconds" not in output
    if case in ("check", "noop"):
        assert lookups == []


@pytest.mark.parametrize("resource_type,uri,object_type", [
    ("chassis", "equipment/Chasses", "equipment.Chassis"),
    ("server", "compute/PhysicalSummaries", "compute.PhysicalSummary"),
])
def test_hardware_serial_query_uses_serial_not_name(monkeypatch, resource_type, uri, object_type):
    from urllib.parse import parse_qs, urlparse

    api_module = importlib.import_module(module.api.__module__)
    kwargs = configuration(check=False)
    serial = "FOX2651P1WQ"
    assert module.serial_regex.fullmatch(serial)
    kwargs.args.debug_level = 0
    kwargs.args.url = "https://intersight.example.test"
    kwargs.api_auth = Mock()
    kwargs.type_dotmap = DotMap
    kwargs.api_body = {}
    kwargs.method = "get"
    kwargs.names = [serial]
    kwargs.uri = uri
    requests = []

    def get(url, **_options):
        requests.append(url)
        params = parse_qs(urlparse(url).query)
        assert params["$filter"] == [f"Serial in ('{serial}')"]
        assert "Name in" not in url
        if "$count" in params:
            return Mock(status_code=200, json=lambda: {"Count": 1})
        return Mock(status_code=200, json=lambda: {
            "Count": 1,
            "Results": [{"Serial": serial, "Name": "not-the-serial",
                         "Moid": "hardware-moid", "ObjectType": object_type}],
        })

    monkeypatch.setattr(api_module.requests, "get", get)
    result = module.api(category="system", type="serial_number").calls(kwargs)
    assert len(requests) == 2
    module.configure(category="profiles", type=resource_type).validate_serial_results([serial], result)
    assert result.intersight_api.system.serial_number[serial].moid == "hardware-moid"
    if resource_type == "chassis":
        result.script_path = str(Path(module.__file__).resolve().parents[2])
        payload = module.configure(category="profiles", type="chassis").create_api_body(
            DotMap({"name": "Chassis", "serial_number": serial}), "", "", result)
        assert payload["AssignedChassis"] == {"Moid": "hardware-moid", "ObjectType": "equipment.Chassis"}
