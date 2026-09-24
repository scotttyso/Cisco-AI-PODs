"""Intersight api class."""
# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates.
# All rights reserved.
# pylint: disable=invalid-name,missing-class-docstring,missing-function-docstring
# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-nested-blocks,no-else-continue,no-else-return
# =============================================================================
# Source Modules
# =============================================================================
import sys
from .. import notifications, pcolor


def prRed(skk):
    print(f"\033[91m {skk}\033[00m")


try:
    from .. import shared_functions
    from copy import deepcopy
    from dotmap import DotMap
    from intersight_auth import IntersightAuth, repair_pem
    import json
    import numpy
    import os
    import re
    import requests
    import time
    import urllib3
except ImportError as e:
    prRed(f'src/intersight/api.py - !!! ERROR !!!\n{e.__class__.__name__}')
    prRed(f" Module {e.name} is required to run this script")
    prRed(f" Install the module using the following: `pip install {e.name}`")
    sys.exit(1)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

parent_regex = re.compile(
    r'^(Parent|((Eth|Fc)Network|(L|S)anConnectivity|Ldap|Port|Storage)Policy)$')
pool_regex = re.compile(
    r'^((ip|iqn|mac|uuid|fc)pool\.((Ip|Uuid)?Lease|Reservation))$')

# =============================================================================
# Intersight -> API Class
# =============================================================================


class api:
    def __init__(self, category=None, type=None):  # pylint: disable=redefined-builtin
        self.category = category
        self.type = type

    # =========================================================================
    # Function - Get All Organizations from Intersight
    # =========================================================================
    def all_organizations(self, kwargs):
        # =====================================================================
        # Get Organization List from the API
        # =====================================================================
        kwargs = kwargs | DotMap(
            api_filter='ignore',
            method='get',
            uri='organization/Organizations')
        kwargs = api(category='system', type=self.type).calls(kwargs)
        return kwargs

    # =========================================================================
    # Function - Process API Results
    # =========================================================================
    def build_intersight_api_dict(self, api_results, kwargs):
        # pcolor.Yellow(f'Build API Dict for {self.category} -> {self.type}')
        pmoids = DotMap()

        def function_org_moids(i, kwargs):
            if i.Name not in kwargs.org_moids:
                kwargs.org_moids[i.Name] = DotMap(moid=i.Moid, tags=i.Tags)
                kwargs.org_names[i.Moid] = i.Name
            return kwargs

        def function_rsg_moids(i, kwargs):
            if i.Name not in kwargs.rsg_moids:
                kwargs.rsg_moids[i.Name] = DotMap(moid=i.Moid, tags=i.Tags)
                kwargs.rsg_names[i.Moid] = i.Name
            return kwargs
        if not kwargs.build_skip and api_results.get('Results'):
            def check_for_dotmap_key(kwargs):
                if not kwargs.get('intersight_api'):
                    kwargs.intersight_api = DotMap()
                if isinstance(
                        kwargs.org,
                        str) and not kwargs.intersight_api.get(
                        kwargs.org):
                    kwargs.intersight_api[kwargs.org] = DotMap()
                return kwargs
            for i in api_results.Results:
                if i.get('Body'):
                    i = i.Body
                ikeys = list(i.keys())
                pool_match = re.search(pool_regex, i.ObjectType)
                if 'system' == self.category:
                    if 'Serial' in ikeys:
                        iname = i.Serial
                    elif 'Key' in ikeys:
                        iname = i.Key
                    elif 'SharedResource' in ikeys:
                        iname = i.Moid
                    elif 'Name' in ikeys:
                        iname = i.Name
                    else:
                        iname = i.Moid
                    if self.type == 'targets':
                        kwargs.intersight_api[self.category][self.type][iname] = DotMap(
                            moid=i.RegisteredDevice.Moid, result=i)
                    else:
                        kwargs.intersight_api[self.category][self.type][iname] = DotMap(
                            moid=i.Moid, result=i)
                    if 'organizations' == self.type:
                        kwargs = function_org_moids(i, kwargs)
                    elif 'resource_groups' == self.type:
                        kwargs = function_rsg_moids(i, kwargs)
                    continue
                elif 'organization.Organization' == i.ObjectType:
                    kwargs = function_org_moids(i, kwargs)
                    continue
                elif (any(re.search(parent_regex, e) for e in ikeys) and isinstance(kwargs.org, str)) or pool_match:
                    if pool_match:
                        child_type = pool_match.group(3).replace(
                            'Ip', '').replace('Uuid', '').lower()
                        if i.get('IdPurpose'):
                            parent_type = i.IdPurpose.lower()
                        elif i.get('PoolPurpose'):
                            parent_type = i.PoolPurpose.lower()
                        else:
                            parent_type = pool_match.group(2)
                        if 'Identity' in ikeys:
                            iname = i.Identity
                        elif 'IpV4Address' in ikeys:
                            iname = i.IpV4Address
                        elif 'IpV6Address' in ikeys:
                            iname = i.IpV6Address
                        elif 'IqnAddress' in ikeys:
                            iname = i.IqnAddress
                        elif 'MacAddress' in ikeys:
                            iname = i.MacAddress
                        elif 'Uuid' in ikeys:
                            iname = i.Uuid
                        elif 'WWnId' in ikeys:
                            iname = i.WWnId
                        elif 'WwnId' in ikeys:
                            iname = i.WwnId
                        parent_name = kwargs.pools[parent_type][i.Pool.Moid].name
                        organization = kwargs.pools[parent_type][i.Pool.Moid].organization
                        kwargs.intersight_api[organization][self.category][parent_type][parent_name][child_type][iname] = DotMap(
                            moid=i.Moid, result=i)
                        continue
                    else:
                        split_name = kwargs.intersight_object_map[i.ObjectType].split(
                            '.')
                        parent_match = next(
                            (e for e in ikeys if re.search(
                                parent_regex, e)), None)
                        parent_type = split_name[0]
                        child_type = split_name[1]
                        if 'PcId' in ikeys:
                            iname = str(i.PcId)
                        elif 'PortId' in ikeys:
                            iname = str(i.PortId)
                        elif 'VlanId' in ikeys:
                            iname = str(i.VlanId)
                        elif 'EndPointUser' in ikeys:
                            iname = i.EndPointUser.Moid
                        elif 'PortIdStart' in ikeys:
                            iname = str(i.PortIdStart)
                        elif 'Server' in ikeys:
                            iname = i.Server
                        elif 'VsanId' in ikeys:
                            iname = str(i.VsanId)
                        elif 'Name' in ikeys:
                            iname = i.Name
                        else:
                            iname = i.Moid
                        parent_name = kwargs.intersight_api[kwargs.org][
                            self.category][parent_type][i[parent_match].Moid]
                        kwargs.intersight_api[kwargs.org][self.category][parent_type][parent_name][child_type][iname] = DotMap(
                            moid=i.Moid, result=i)
                        continue
                elif 'Name' in ikeys and isinstance(self.category, str):
                    # fcpool.Pool backs both wwnn and wwpn; keep the requested
                    # pool type to avoid collapsing both into a single key.
                    if self.category == 'pools' and i.ObjectType == 'fcpool.Pool' and self.type in [
                            'wwnn', 'wwpn']:
                        ptype = self.type
                    else:
                        ptype = kwargs.intersight_object_map[i.ObjectType]
                    kwargs = check_for_dotmap_key(kwargs)
                    iname = i.Name
                    kwargs.intersight_api[kwargs.org][self.category][ptype][iname] = DotMap(
                        moid=i.Moid, result=i, tags=i.Tags)
                    kwargs.intersight_api[kwargs.org][self.category][ptype][i.Moid] = iname
                    continue
                elif 'Name' in ikeys:
                    iname = i.Name
                elif i.ObjectType == 'asset.DeviceRegistration':
                    iname = i.Serial[0]
                elif 'Serial' in ikeys:
                    iname = i.Serial
                elif 'Answers' in ikeys:
                    iname = i.Answers.Hostname
                elif self.type == 'upgrade' and i.Status == 'IN_PROGRESS':
                    iname = kwargs.srv_moid
                elif 'SocketDesignation' in ikeys:
                    iname = i.Dn
                elif 'Version' in ikeys:
                    iname = i.Version
                elif 'ControllerId' in ikeys:
                    iname = i.ControllerId
                elif 'PciSlot' in ikeys:
                    iname = str(i.PciSlot)
                else:
                    iname = i.Moid
                if 'Organization' in ikeys and i.ObjectType.endswith('.Policy'):
                    organization = kwargs.org_names.get(i.Organization.Moid)
                    policy_type = kwargs.intersight_object_map[i.ObjectType]
                    if organization:
                        if not kwargs.intersight_api.get(organization):
                            kwargs.intersight_api[organization] = DotMap()
                        if not kwargs.intersight_api[organization].get('policies'):
                            kwargs.intersight_api[organization].policies = DotMap()
                        if not kwargs.intersight_api[organization].policies.get(policy_type):
                            kwargs.intersight_api[organization].policies[policy_type] = DotMap()
                        kwargs.intersight_api[organization].policies[policy_type][iname] = DotMap(
                            moid=i.Moid, result=i)
                if 'ConfiguredBootMode' in ikeys:
                    pmoids[iname].boot_mode = i.ConfiguredBootMode
                if 'EnforceUefiSecureBoot' in ikeys:
                    pmoids[iname].enable_secure_boot = i.EnforceUefiSecureBoot
                if 'IpV4Config' in ikeys:
                    pmoids[iname].ipv4_config = i.IpV4Config
                if 'IpV6Config' in ikeys:
                    pmoids[iname].ipv6_config = i.IpV6Config
                if 'ManagementMode' in ikeys:
                    pmoids[iname].management_mode = i.ManagementMode
                if 'MgmtIpAddress' in ikeys:
                    pmoids[iname].management_ip_address = i.MgmtIpAddress
                if 'Model' in ikeys:
                    pmoids[iname].model = i.Model
                    pmoids[iname].name = i.Name
                    pmoids[iname].object_type = i.ObjectType
                    pmoids[iname].registered_device = i.RegisteredDevice.Moid
                    if 'ChassisId' in ikeys:
                        pmoids[iname].id = i.ChassisId
                    if 'SourceObjectType' in ikeys:
                        pmoids[iname].object_type = i.SourceObjectType
                if 'Organization' in ikeys:
                    pmoids[iname].organization = kwargs.org_names[i.Organization.Moid]
                if 'PolicyBucket' in ikeys:
                    pmoids[iname].policy_bucket = i.PolicyBucket
                if 'Selectors' in ikeys:
                    pmoids[iname].selectors = i.Selectors
                if 'SwitchId' in ikeys:
                    pmoids[iname].switch_id = i.SwitchId
                if 'Tags' in ikeys:
                    pmoids[iname].tags = i.Tags
                if 'UpgradeStatus' in ikeys:
                    pmoids[iname].upgrade_status = i.UpgradeStatus
                if 'WorkflowInfo' in ikeys:
                    if not isinstance(i.WorkflowInfo, kwargs.type_none):
                        pmoids[iname].workflow_moid = i.WorkflowInfo.Moid
                if 'Distributions' in ikeys:
                    pmoids[iname].distributions = [
                        e.Moid for e in i.Distributions]
                if 'Source' in ikeys and 'LocationLink' in ikeys:
                    pmoids[iname].url = i.Source.LocationLink
                if 'Vendor' in ikeys and not isinstance(i.Vendor, str):
                    pmoids[iname].vendor_moid = i.Vendor.Moid
                if 'Profiles' in ikeys and i.Profiles is not None:
                    pmoids[iname].profiles = []
                    for x in i.Profiles:
                        xdict = DotMap(Moid=x.Moid, ObjectType=x.ObjectType)
                        pmoids[iname].profiles.append(xdict)
            kwargs.pmoids = pmoids
        return kwargs

    # =========================================================================
    # Function - Perform API Calls against Intersight
    # =========================================================================
    def calls(self, kwargs):
        # =====================================================================
        # Global options for debugging
        # 1 - Shows the api request response status code
        # 5 - Show URL String + Lower Options
        # 6 - Adds Results + Lower Options
        # 7 - Adds json payload + Lower Options
        # Note: payload shows as pretty and straight to check
        #       for stray object types like Dotmap and numpy
        # =====================================================================
        debug_level = kwargs.args.debug_level
        # =====================================================================
        # Authenticate to the API
        # =====================================================================
        org_moid = None
        if not re.search('^(organization|resource)/', kwargs.uri):
            org_moid = kwargs.org_moids[kwargs.org].moid
        # =====================================================================
        # Authenticate to the API
        # =====================================================================

        def api_auth_function(kwargs):
            api_key_id = kwargs.args.intersight_api_key_id
            secret_key = kwargs.args.intersight_secret_key
            if os.path.isfile(secret_key):
                kwargs.api_auth = IntersightAuth(
                    api_key_id=api_key_id, secret_key_filename=secret_key)
            elif re.search(r'\n', secret_key):
                kwargs.api_auth = IntersightAuth(
                    api_key_id=api_key_id, secret_key_string=secret_key)
            else:
                kwargs.api_auth = IntersightAuth(
                    api_key_id=api_key_id, secret_key_string=repair_pem(secret_key))
            kwargs.auth_time = time.time()
            return kwargs
        if not kwargs.get('api_auth'):
            kwargs = api_auth_function(kwargs)
        # =====================================================================
        # Setup API Parameters
        # =====================================================================

        def api_calls(kwargs):
            # =================================================================
            # Perform the apiCall
            # =================================================================
            if isinstance(kwargs.api_body, kwargs.type_dotmap):
                kwargs.api_body = kwargs.api_body.toDict()
            aargs = kwargs.api_args
            aauth = kwargs.api_auth
            method = kwargs.method
            moid = kwargs.pmoid
            payload = kwargs.api_body
            retries = 3
            uri = kwargs.uri
            url = f'{kwargs.args.url}/api/v1'

            def send_error(kwargs, response):
                pcolor.Red(json.dumps(kwargs.api_body, indent=4))
                pcolor.Red('!!! ERROR !!!')
                if method == 'get_by_moid':
                    pcolor.Red(f'  URL: {url}/{uri}/{moid}')
                elif method == 'delete':
                    pcolor.Red(f'  URL: {url}/{uri}/{moid}')
                elif method == 'get':
                    pcolor.Red(f'  URL: {url}/{uri}{aargs}')
                elif method == 'patch':
                    pcolor.Red(f'  URL: {url}/{uri}/{moid}')
                elif method == 'post_by_moid':
                    pcolor.Red(f'  URL: {url}/{uri}/{moid}')
                elif method == 'post':
                    pcolor.Red(f'  URL: {url}/{uri}')
                pcolor.Red(f'  Running Process: {method} {self.type}')
                if response is None:
                    pcolor.Red('    Error status is unavailable (request failed before response).')
                    sys.exit(1)
                pcolor.Red(f'    Error status is {response}')
                if '{' in response.text:
                    for k, v in (response.json()).items():
                        pcolor.Red(f"    {k} is '{v}'")
                else:
                    pcolor.Red(response.text)
                sys.exit(1)
            response = None
            for i in range(retries):
                try:
                    if method == 'get_by_moid':
                        response = requests.get(
                            f'{url}/{uri}/{moid}', verify=False, auth=aauth, timeout=120)
                    elif method == 'delete':
                        response = requests.delete(
                            f'{url}/{uri}/{moid}', verify=False, auth=aauth, timeout=120)
                    elif method == 'get':
                        response = requests.get(
                            f'{url}/{uri}{aargs}', verify=False, auth=aauth, timeout=120)
                    elif method == 'patch':
                        response = requests.patch(
                            f'{url}/{uri}/{moid}', verify=False, auth=aauth, json=payload, timeout=120)
                    elif method == 'post_by_moid':
                        response = requests.post(
                            f'{url}/{uri}/{moid}', verify=False, auth=aauth, json=payload, timeout=120)
                    elif method == 'post':
                        response = requests.post(
                            f'{url}/{uri}', verify=False, auth=aauth, json=payload, timeout=120)

                    status = response.status_code

                    # Success
                    if 200 <= status < 300:
                        break

                    # Retryable API states
                    retry_action = False
                    if status in (400, 403, 409):
                        try:
                            for v in response.json().values():
                                if isinstance(v, str) and (
                                    'user_action_is_not_allowed' in v or
                                    'policy_attached_to_multiple_profiles_cannot_be_edited' in v
                                ):
                                    retry_action = True
                                    break
                        except Exception:  # pylint: disable=broad-exception-caught
                            retry_action = False

                    if retry_action and i < retries - 1:
                        pcolor.Purple(
                            '     **NOTICE** Profile in Validating State. Sleeping for 45 seconds and retrying.')
                        time.sleep(45)
                        continue

                    # Non-fatal special cases
                    text = response.text or ''
                    if 'Your token has expired' in text or status == 404:
                        kwargs.results = False
                        return kwargs
                    if 'There is an upgrade already running' in text:
                        kwargs.running = True
                        return kwargs

                    # Only hard-fail in final else path
                    send_error(kwargs, response)

                except requests.RequestException as e:
                    if 'Your token has expired' in str(
                            e) or 'Not Found' in str(e):
                        kwargs.results = False
                        return kwargs
                    elif 'user_action_is_not_allowed' in str(e):
                        if i < retries - 1:
                            time.sleep(45)
                            continue
                        else:
                            raise
                    elif 'There is an upgrade already running' in str(e):
                        kwargs.running = True
                        return kwargs
                    else:
                        pcolor.Red(
                            f"Exception when calling {url}/{uri}: {e}\n")
                        raise
            # =================================================================
            # Print Debug Information if Turned on
            # =================================================================
            api_results = DotMap(response.json())
            if int(debug_level) >= 1:
                pcolor.Cyan(f'RESPONSE: {str(response)}')
            if int(debug_level) >= 5:
                if method == 'get_by_moid':
                    pcolor.Cyan(f'URL:      {url}/{uri}/{moid}')
                elif method == 'get':
                    pcolor.Cyan(f'URL:      {url}/{uri}{aargs}')
                elif method == 'patch':
                    pcolor.Cyan(f'URL:      {url}/{uri}/{moid}')
                elif method == 'post_by_moid':
                    pcolor.Cyan(f'URL:      {url}/{uri}/{moid}')
                elif method == 'post':
                    pcolor.Cyan(f'URL:      {url}/{uri}')
            if int(debug_level) >= 6:
                pcolor.Cyan('HEADERS:')
                pcolor.Cyan(json.dumps(dict(response.headers), indent=4))
                if payload:
                    pcolor.Cyan('PAYLOAD:')
                    pcolor.Cyan(json.dumps(payload, indent=4))
            if int(debug_level) == 7:
                pcolor.Cyan(json.dumps(api_results, indent=4))
            # =================================================================
            # Gather Results from the apiCall
            # =================================================================
            results_keys = list(api_results.keys())
            if 'Results' in results_keys:
                kwargs.results = api_results.Results
            else:
                kwargs.results = api_results
            if not kwargs.build_skip:
                kwargs.build_skip = False
            if 'post' in method:
                if api_results.get('Responses'):
                    api_results['Results'] = deepcopy(api_results['Responses'])
                    kwargs = self.build_intersight_api_dict(
                        api_results, kwargs)
                elif re.search('bulk.(MoCloner|Request)', api_results.ObjectType):
                    kwargs = self.build_intersight_api_dict(
                        api_results, kwargs)
                else:
                    kwargs.pmoid = api_results.Moid
                    if kwargs.api_body.get('Name'):
                        kwargs.pmoids[kwargs.api_body['Name']] = kwargs.pmoid
            elif 'inventory' in kwargs.uri:
                pass
            elif not kwargs.build_skip:
                kwargs = self.build_intersight_api_dict(api_results, kwargs)
            # =================================================================
            # Print Progress Notifications
            # =================================================================
            if re.search('(patch|post)', method):
                if api_results.get('Responses'):
                    for e in api_results.Responses:
                        kwargs.api_results = e.Body
                        notifications.completed_item(
                            self.category, self.type, kwargs)
                elif re.search('bulk.(Request|RestResult)', api_results.ObjectType):
                    for e in api_results.Results:
                        kwargs.api_results = e.Body
                        if re.search(
                            'bulk.(Request|RestResult)',
                                api_results.ObjectType):
                            if e.Body.get('Name'):
                                name_key = 'Name'
                            elif e.Body.get('Identity'):
                                name_key = 'Identity'
                            elif e.Body.get('PcId'):
                                name_key = 'PcId'
                            elif e.Body.get('PortId'):
                                name_key = 'PortId'
                            elif e.Body.get('PortIdStart'):
                                name_key = 'PortIdStart'
                            elif e.Body.get('Server'):
                                name_key = 'Server'
                            elif e.Body.get('VlanId'):
                                name_key = 'VlanId'
                            elif e.Body.get('VsanId'):
                                name_key = 'VsanId'
                            elif e.Body.ObjectType == 'iam.EndPointUserRole':
                                pass
                            else:
                                pcolor.Red(json.dumps(e.Body, indent=4))
                                raise RuntimeError(
                                    f'Bulk API response for {self.type!r} '
                                    'does not contain a recognized identity '
                                    f'field: {json.dumps(e.Body, default=str)}')
                            if not e.Body['ObjectType'] == 'iam.EndPointUserRole':
                                indx = next(
                                    (index for (
                                        index,
                                        d) in enumerate(
                                        kwargs.api_body['Requests']) if d['Body'][name_key] == e.Body[name_key]),
                                    None)
                                kwargs.method = (
                                    kwargs.api_body['Requests'][indx]['Verb']).lower()
                        notifications.completed_item(
                            self.category, self.type, kwargs)
                else:
                    kwargs.api_results = api_results
                    notifications.completed_item(
                        self.category, self.type, kwargs)
            return kwargs
        # =====================================================================
        # Pagenation for Get > 1000
        # =====================================================================
        kwargs_keys = list(kwargs.keys())
        if kwargs.method == 'get':
            def build_api_args(kwargs_keys, kwargs):
                scategory = self.category
                stype = self.type
                if 'api_filter' not in kwargs_keys:
                    regex1 = re.compile(
                        'moid_filter|registered_device|workflow_os_install')
                    regex2 = re.compile('(ip|iqn|mac|uuid|wwnn|wwpn)_leases')
                    if re.search('(vlans|vsans)', self.type):
                        names = ", ".join(map(str, kwargs.names))
                    else:
                        names = "', '".join(kwargs.names)
                    if re.search('organizations|resource_groups', self.type):
                        api_filter = f"Name in ('{names}')"
                    elif self.category == 'system':
                        sregex = re.compile(
                            '^(blades|chassis|domain|rackmounts|server)')
                        if 'iam_end_point_role' == self.type:
                            api_filter = f"Name in ('{names}') and Type eq 'IMC'"
                        elif 'iam_sharing_rules' == self.type:
                            api_filter = f"SharedResource/Moid in ('{names}')"
                        elif 'path_tags' == self.type:
                            api_filter = f"Key in ('{names}')"
                        elif re.search(sregex, self.type):
                            api_filter = f"Serial in ('{names}')"
                        else:
                            api_filter = f"Name in ('{names}')"
                    elif 'pools' in scategory and '.leases' in stype:
                        api_filter = f"Pool/Moid in ('{names}')"
                    elif 'pools' in scategory and '.reservations' in stype:
                        api_filter = f"Pool/Moid in ('{names}')"
                    elif 'ancestors' == self.type:
                        api_filter = f"Ancestors/any(t:t/Moid in ('{names}'))"
                    elif 'asset_target' == self.type:
                        api_filter = f"TargetId in ('{names}')"
                    elif 'connectivity.v' in self.type:
                        api_filter = f"Parent/Moid in ('{names}')"
                    elif 'hcl_status' == self.type:
                        api_filter = f"ManagedObject/Moid in ('{names}')"
                    elif 'iam_end_point_role' == self.type:
                        api_filter = f"Name in ('{names}') and Type eq 'IMC'"
                    elif 'iqn_pool_leases' == self.type:
                        api_filter = f"AssignedToEntity.Moid in ('{names}')"
                    elif 'multi_org' in self.type:
                        api_filter = f"Organization.Moid in ('{names}')"
                    elif re.search('ldap.ldap_', self.type):
                        api_filter = f"LdapPolicy/Moid in ('{names}')"
                    elif 'parent_moids' in self.type:
                        api_filter = f"{kwargs.parent}/Moid in ('{names}')"
                    elif 'port.port_' in self.type:
                        api_filter = f"Parent/Moid in ('{names}')"
                    elif 'profile_moid' == self.type:
                        api_filter = f"Profile.Moid in ('{names}')"
                    elif re.search(regex1, self.type):
                        api_filter = f"Moid in ('{names}')"
                    elif re.search(regex2, self.type):
                        api_filter = f"{kwargs.pkey} in ('{names}')"
                    elif 'registered_device' in self.type:
                        api_filter = f"RegisteredDevice.Moid in ('{names}')"
                    elif 'reservations' in self.type:
                        api_filter = f"Identity in ('{names}')"
                    elif 'serial_number' == self.type:
                        api_filter = f"Serial in ('{names}')"
                    elif 'storage.drive_groups' == self.type:
                        api_filter = f"Parent/Moid in ('{names}')"
                    elif '.switch' in stype and 'templates' == scategory:
                        api_filter = f"SwitchClusterProfileTemplate/Moid in ('{names}')"
                    elif '.switch' in self.type:
                        api_filter = f"SwitchClusterProfile/Moid in ('{names}')"
                    elif 'user_role' == self.type:
                        api_filter = f"EndPointUser/Moid in ('{names}') and EndPointUserPolicy/Moid eq '{kwargs.pmoid}'"
                    elif re.search('v.an\\.v.ans', self.type):
                        api_filter = f"Parent/Moid in ('{names}')"
                    elif 'wwnn_pool_leases' == self.type:
                        api_filter = f"PoolPurpose eq 'WWNN' and AssignedToEntity/Moid in ('{names}')"
                    elif 'wwpn_pool_leases' == self.type:
                        api_filter = f"PoolPurpose eq 'WWPN' and AssignedToEntity/Moid in ('{names}')"
                    else:
                        if org_moid:
                            api_filter = f"Name in ('{names}') and Organization.Moid eq '{org_moid}'"
                        else:
                            api_filter = f"Name in ('{names}')"
                    if re.search('ww(n|p)n.(leases|reservations)', self.type):
                        pass
                    elif re.search('ww(n|p)n', self.type):
                        api_filter = api_filter + \
                            f" and PoolPurpose eq '{self.type.upper()}'"
                    api_args = f'?$filter={api_filter}'
                elif kwargs.api_filter == '':
                    api_args = ''
                elif kwargs.api_filter == 'ignore':
                    api_args = ''
                else:
                    api_args = f'?$filter={kwargs.api_filter}'
                if 'expand' in kwargs_keys:
                    if api_args == '':
                        api_args = f'?$expand={kwargs.expand}'
                    else:
                        api_args = api_args + f'&$expand={kwargs.expand}'
                if 'order_by' in kwargs_keys:
                    if api_args == '':
                        api_args = f'?$orderby={kwargs.order_by}'
                    else:
                        api_args = api_args + f'&$orderby={kwargs.order_by}'
                return api_args

            if len(kwargs.names) > 100:
                chunked_list = []
                chunk_size = 100
                for i in range(0, len(kwargs.names), chunk_size):
                    chunked_list.append(kwargs.names[i:i + chunk_size])
                results = []
                moid_dict = {}
                parent_moid = kwargs.pmoid
                for i in chunked_list:
                    kwargs.names = i
                    kwargs.api_args = build_api_args(kwargs_keys, kwargs)
                    if re.search(
                        'leases|port.port|reservations|user_role|vhbas|vlans|vsans|vnics',
                            self.type):
                        kwargs.pmoid = parent_moid
                    kwargs = api_calls(kwargs)
                    results.extend(kwargs.results)
                    moid_dict = dict(moid_dict, **kwargs.pmoids.toDict())
                kwargs.pmoids = DotMap(moid_dict)
                kwargs.results = results
            else:
                api_args = build_api_args(kwargs_keys, kwargs)
                if '?' in api_args:
                    kwargs.api_args = api_args + '&$count=True'
                else:
                    kwargs.api_args = api_args + '?$count=True'
                prev_build_skip = kwargs.get('build_skip', False)
                kwargs.build_skip = True
                kwargs = api_calls(kwargs)
                kwargs.build_skip = prev_build_skip
                if re.search(
                    'expand.+HostEthIfs',
                        api_args) and kwargs.results.Count > 100:
                    rcount = 1001
                elif re.search('expand.+PhysicalDisks', api_args) and kwargs.results.Count > 30:
                    rcount = 1001
                elif re.search('expand.+Processors', api_args) and kwargs.results.Count > 250:
                    rcount = 1001
                elif re.search('expand.+Units', api_args) and kwargs.results.Count > 30:
                    rcount = 1001
                elif re.search('expand.+Adapters', api_args) and kwargs.results.Count > 500:
                    rcount = 1001
                else:
                    rcount = kwargs.results.Count
                if rcount <= 100:
                    kwargs.api_args = api_args
                    kwargs = api_calls(kwargs)
                elif 100 < rcount <= 1000:
                    if '?' in api_args:
                        kwargs.api_args = api_args + '&$top=1000'
                    else:
                        kwargs.api_args = api_args + '?$top=1000'
                    kwargs = api_calls(kwargs)
                elif rcount > 1000:
                    if re.search('expand.+HostEthIfs', api_args):
                        get_count = kwargs.results.Count
                        top_count = kwargs.results.Count // 10
                    elif re.search('expand.+PhysicalDisks', api_args):
                        get_count = kwargs.results.Count
                        top_count = kwargs.results.Count // 24
                    elif re.search('expand.+Processors', api_args):
                        get_count = kwargs.results.Count
                        top_count = kwargs.results.Count // 4
                    elif re.search('expand.+Units', api_args):
                        get_count = kwargs.results.Count
                        top_count = kwargs.results.Count // 32
                    elif re.search('expand.+Adapters', api_args):
                        get_count = kwargs.results.Count
                        top_count = kwargs.results.Count // 4
                    else:
                        get_count = rcount
                        top_count = 1000
                    moid_dict = {}
                    offset_count = 0
                    results = []
                    while get_count > 0:
                        if '?' in api_args:
                            kwargs.api_args = api_args + \
                                f'&$top={top_count}&$skip={offset_count}'
                        else:
                            kwargs.api_args = api_args + \
                                f'?$top={top_count}&$skip={offset_count}'
                        kwargs = api_calls(kwargs)
                        results.extend(kwargs.results)
                        moid_dict = dict(moid_dict, **kwargs.pmoids.toDict())
                        get_count = get_count - top_count
                        offset_count = offset_count + top_count
                    kwargs.pmoids = DotMap(moid_dict)
                    kwargs.results = results
        else:
            kwargs.api_args = ''
            kwargs = api_calls(kwargs)
        # =====================================================================
        # Return kwargs
        # =====================================================================
        for e in ['api_filter', 'build_skip', 'expand', 'order_by']:
            if e in kwargs_keys:
                kwargs.pop(e)
        return kwargs

    # =========================================================================
    # Function - Get Organizations from Intersight
    # =========================================================================
    def organizations(self, kwargs):
        # =====================================================================
        # Functions to Create Resource Groups and Organizations
        # =====================================================================
        def create_resource_group(rg, org, kwargs):
            api_body = {'Description': f'{rg} Resource Group', 'Name': rg}
            kwargs = kwargs | DotMap(
                api_body=api_body,
                method='post',
                org=org,
                uri='resource/Groups')
            kwargs = api('resource_groups').calls(kwargs)
            if rg not in kwargs.rsg_moids:
                kwargs.rsg_moids[rg] = DotMap()
            kwargs.rsg_moids[rg].moid = kwargs.results.Moid
            kwargs.rsg_moids[rg].selectors = kwargs.results.Selectors
            return kwargs

        def create_org_api_call(api_body, org, kwargs):
            kwargs = kwargs | DotMap(
                api_body=api_body,
                method='post',
                uri='organization/Organizations')
            kwargs = api(self.type).calls(kwargs)
            kwargs.org_moids[org].moid = kwargs.results.Moid
            return kwargs

        def create_shared_organization(o, kwargs):
            api_body = {'Description': f'{o} Organization', 'Name': o}
            kwargs = create_org_api_call(api_body, o, kwargs)
            return kwargs

        def create_org_question(org, kwargs):
            if kwargs.args.non_interactive:
                return True
            kwargs.jdata = DotMap(
                default=True,
                description=f'  The organization `{org}` does not exist.  Do you want to create it?',
                sort=False,
                title='Intersight Organization',
                type='boolean')
            return shared_functions.variable_prompt(kwargs)

        def organization_type(org, kwargs):
            if kwargs.args.non_interactive:
                return 'Targets'
            kwargs.jdata = DotMap(
                default='Targets',
                description=f'  Will the organization `{org}` be shared with other organizations, or will you be assigning targets (servers, domains, etc.)?',
                enum=[
                    'Shared',
                    'Targets'],
                sort=False,
                title='Intersight Organization',
                type='string')
            return shared_functions.variable_prompt(kwargs)

        def create_organization(org, okeys, kwargs):
            if 'resource_groups' in okeys and len(
                    kwargs.imm_dict.orgs[org].resource_groups) > 0:
                for rg in kwargs.imm_dict.orgs[org].resource_groups:
                    if rg not in list(kwargs.rsg_moids.keys()):
                        kwargs = create_resource_group(rg, org, kwargs)
                rgs = [{'Moid': kwargs.rsg_moids[rg].moid, 'ObjectType': 'resource.Group'}
                       for rg in kwargs.imm_dict.orgs[org].resource_groups]
                api_body = {
                    'Description': f'{org} Organization',
                    'Name': org,
                    'ResourceGroups': rgs}
                kwargs = create_org_api_call(api_body, org, kwargs)
            elif 'organizations_to_share_with' in okeys and len(kwargs.imm_dict.orgs[org].organizations_to_share_with) > 0:
                for o in kwargs.imm_dict.orgs[org].organizations_to_share_with:
                    if o not in list(kwargs.org_moids.keys()):
                        create_org = create_org_question(o, kwargs)
                        if create_org:
                            kwargs = create_shared_organization(o, kwargs)
                        else:
                            notifications.error_organization(o)
                shared_orgs = [{'Moid': kwargs.org_moids[o].moid, 'ObjectType': 'organization.Organization'}
                               for o in kwargs.imm_dict.orgs[org].organizations_to_share_with]
                api_body = {
                    'Description': f'{org} Organization',
                    'Name': org,
                    'SharedWithResources': shared_orgs}
                kwargs = create_org_api_call(api_body, org, kwargs)
            else:
                org_type = organization_type(org, kwargs)
                if org_type == 'Shared':
                    api_body = {
                        'Description': f'{org} Organization',
                        'Name': org,
                        'SharedWithResources': []}
                    kwargs = create_org_api_call(api_body, org, kwargs)
                else:
                    kwargs = create_resource_group(org, org, kwargs)
                    api_body = {'Description': f'{org} Organization', 'Name': org, 'ResourceGroups': [
                        {'Moid': kwargs.rsg_moids[org].moid, 'ObjectType': 'resource.Group'}]}
                    kwargs = create_org_api_call(api_body, org, kwargs)
            return kwargs
        if self.type == 'resource_groups':
            kwargs = kwargs | DotMap(
                method='get',
                names=kwargs.resource_groups,
                uri='resource/Groups')
            kwargs = api('resource_groups').calls(kwargs)
            kwargs.rsg_results = kwargs.rsg_results + kwargs.results
            for e in kwargs.pmoids:
                kwargs.rsg_moids[e] = DotMap(kwargs.pmoids[e])
            for rsg in kwargs.resource_groups:
                if rsg not in list(kwargs.rsg_moids.keys()):
                    kwargs = create_resource_group(rsg, rsg, kwargs)
        else:
            # =====================================================================
            # Get Resource Groups from the API
            # =====================================================================
            rsg_list = []
            for org in kwargs.orgs:
                rsg_keys = list(kwargs.imm_dict.orgs[org].keys())
                if 'resource_groups' in rsg_keys and len(
                        kwargs.imm_dict.orgs[org].resource_groups) > 0:
                    for rg in kwargs.imm_dict.orgs[org].resource_groups:
                        rsg_list.append(rg)
            names = list(numpy.unique(numpy.array(rsg_list + kwargs.orgs)))
            kwargs = kwargs | DotMap(
                method='get', names=names, uri='resource/Groups')
            kwargs = api(
                category=self.category,
                type='resource_groups').calls(kwargs)
            kwargs = kwargs | DotMap(
                rsg_moids=kwargs.pmoids,
                rsg_results=kwargs.results)
            # =====================================================================
            # Get Organizations from the API
            # =====================================================================
            kwargs = kwargs | DotMap(
                method='get',
                names=kwargs.orgs,
                uri='organization/Organizations')
            kwargs = api(
                category=self.category,
                type='organizations').calls(kwargs)
            kwargs = kwargs | DotMap(
                org_moids=kwargs.pmoids,
                org_results=kwargs.results)
            # =====================================================================
            # Loop thru the List of Organizations and Create if They Don't Exist
            # =====================================================================
            okeys = list(kwargs.org_moids.keys())
            for org in kwargs.orgs:
                if org not in okeys:
                    okeys = list(kwargs.imm_dict.orgs[org].keys())
                    if 'create_organization' in okeys and kwargs.imm_dict.orgs[
                            org].create_organization:
                        kwargs = create_organization(org, okeys, kwargs)
                    else:
                        create_org = create_org_question(org, kwargs)
                        if create_org:
                            kwargs = create_organization(org, okeys, kwargs)
                        else:
                            notifications.error_organization(org)
        return kwargs
