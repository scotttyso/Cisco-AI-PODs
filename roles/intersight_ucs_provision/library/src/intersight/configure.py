"""Intersight configure class."""
# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates.
# All rights reserved.
# pylint: disable=invalid-name,missing-class-docstring,missing-function-docstring
# pylint: disable=too-many-branches,too-many-statements,too-many-locals,too-many-lines
# pylint: disable=too-many-nested-blocks,no-member,import-outside-toplevel
# pylint: disable=too-many-return-statements,no-else-return,unused-argument
# =============================================================================
# Source Modules
# =============================================================================
import sys
from .. import notifications, pcolor


def prRed(skk):
    print(f"\033[91m {skk}\033[00m")


try:
    from .. import shared_functions
    from .api import api
    from OpenSSL import crypto
    from copy import deepcopy
    from datetime import datetime
    from dotmap import DotMap
    from operator import itemgetter
    import base64
    import jinja2
    import json
    import numpy
    import os
    import re
    import time
except ImportError as e:
    prRed(
        f'src/intersight/configure.py - !!! ERROR !!!\n{e.__class__.__name__}')
    prRed(f" Module {e.name} is required to run this script")
    prRed(f" Install the module using the following: `pip install {e.name}`")
    sys.exit(1)

serial_regex = re.compile(
    '^[A-Z]{3}[2-3][\\d]([0][1-9]|[1-4][0-9]|[5][0-3])[\\dA-Z]{4}$')
template_regex = re.compile(r'^(ucs_(server|chassis)(_profile)?_template)$')


def system(*args, **kwargs):
    from .system import system as _system
    return _system(*args, **kwargs)


DESCRIPTION_WORD_MAP = {
    'policies': 'Policy',
    'pools': 'Pool',
    'profiles': 'Profile',
    'templates': 'Template',
    'system': 'System'
}

# =============================================================================
# Intersight -> Configure Class
# =============================================================================


class configure:
    def __init__(self, category=None, type=None):  # pylint: disable=redefined-builtin
        self.category = category
        self.type = type

    # =========================================================================
    # Function - API Get Calls
    # =========================================================================
    def api_get(self, empty=False, names=None, otype=None, kwargs=None):
        if names is None:
            names = []
        if kwargs is None:
            kwargs = DotMap()
        if otype is None:
            otype = self.type
        # =====================================================================
        # Function - Exit on Empty Results
        # =====================================================================

        def empty_results(org, names, kwargs):
            pcolor.Red(f"The API Query Results were empty for {kwargs.uri}.")
            pcolor.Red(f"  Organization: {org}")
            pcolor.Red(f"  Names: `{', '.join(names)}`")
            pcolor.Red("Exiting...")
            raise ValueError(
                f"Empty API query results for {kwargs.uri} (organization={org}, names={', '.join(names)})")

        original_org = kwargs.org
        kwargs.glist = DotMap()
        for e in names:
            org, policy = self.determine_resource_organization(
                False, e, kwargs)
            if not kwargs.glist[org].names:
                kwargs.glist[org].names = []
            kwargs.glist[org].names.append(policy)
        orgs = list(kwargs.glist.keys())
        missing_orgs = False
        for org in orgs:
            if org not in kwargs.org_moids:
                kwargs.orgs.append(org)
                missing_orgs = True
        if missing_orgs:
            kwargs = api(category=self.category,
                         type='organizations').organizations(kwargs)
        for org in orgs:
            names = kwargs.glist[org].names
            kwargs = kwargs | DotMap(
                names=names,
                org=org,
                method='get',
                uri=kwargs.ezdata[f"intersight.{self.category}.{otype}"]['x-intersight-uri'])
            kwargs = api(category=self.category, type=otype).calls(kwargs)
            if not empty and kwargs.results == []:
                empty_results(org, names, kwargs)
            elif empty and kwargs.results == []:
                pcolor.Yellow(
                    f"  * API Query Results were empty for {kwargs.uri} with Organization: {org}")
                pcolor.Yellow(
                    f"    - Names: `{', '.join(names)}`.  Continuing...")
                continue
        kwargs.org = original_org
        return kwargs

    # =========================================================================
    # Function - Lookup Certificate and Private Key Files, Check for Validity, and Return Contents
    # =========================================================================
    def cert_file_check(self, expected_type, file_path, item):
        # Expand ~ to home directory
        file_path = os.path.expanduser(file_path)
        if not isinstance(file_path, str) or len(file_path.strip()) == 0:
            pcolor.Red(
                f'!!! ERROR !!! `{expected_type}` file path is empty for certificate policy `{item.name}`.')
            raise ValueError(
                f'`{expected_type}` file path is empty for certificate policy `{item.name}`')
        if not os.path.isfile(file_path):
            pcolor.Red(
                f'!!! ERROR !!! `{expected_type}` file `{file_path}` was not found for certificate policy `{item.name}`.')
            raise FileNotFoundError(
                f'`{expected_type}` file `{file_path}` was not found for certificate policy `{item.name}`')
        try:
            with open(file_path, 'r', encoding='utf-8') as cert_file:
                cert_content = cert_file.read()
        except OSError as exc:
            pcolor.Red(
                f'!!! ERROR !!! Failed to read `{expected_type}` file `{file_path}` for certificate policy `{item.name}`: {exc}')
            raise OSError(
                f'Failed to read `{expected_type}` file `{file_path}` for certificate policy `{item.name}`') from exc

        if 'BEGIN CERTIFICATE' in cert_content:
            try:
                crypto.load_certificate(crypto.FILETYPE_PEM, cert_content)
            except Exception as exc:
                pcolor.Red(
                    f'!!! ERROR !!! `{file_path}` is not a valid PEM certificate: {exc}')
                raise ValueError(
                    f'`{file_path}` is not a valid PEM certificate') from exc
            detected_type = 'certificate'
        elif 'PRIVATE KEY' in cert_content:
            try:
                crypto.load_privatekey(crypto.FILETYPE_PEM, cert_content)
            except Exception as exc:
                pcolor.Red(
                    f'!!! ERROR !!! `{file_path}` is not a valid PEM private key: {exc}')
                raise ValueError(
                    f'`{file_path}` is not a valid PEM private key') from exc
            detected_type = 'private_key'
        else:
            pcolor.Red(
                f'!!! ERROR !!! `{file_path}` is not a valid PEM certificate or private key file.')
            raise ValueError(
                f'`{file_path}` is not a valid PEM certificate or private key file')
        if detected_type != expected_type:
            pcolor.Red(
                f'!!! ERROR !!! `{file_path}` contains a `{detected_type}` but `{expected_type}` was expected.')
            raise ValueError(
                f'`{file_path}` contains `{detected_type}` but `{expected_type}` was expected')
        cert_content = base64.b64encode(
            cert_content.encode('utf-8')).decode('utf-8')

        return cert_content

    # =========================================================================
    # Function - Assign Children Resources to Parent Resources
    # =========================================================================
    def children_check_parent(self, child_type, kwargs):
        org = kwargs.org
        np, ns = self.name_prefix_suffix(kwargs.org, kwargs)
        # =====================================================================
        # Get Existing Assignments for Each Parent Policy.
        # Skip if No Parent Policies Exist or if Running in Check Mode.
        # =====================================================================
        continue_count = 0
        ikeys = list(kwargs.intersight_api[org]
                     [self.category][self.type].keys())
        pcategory = self.category.replace('_', ' ').title()
        ptitle = notifications.mod_pol_description(
            (self.type.replace('_', ' ').title()))
        for e in kwargs.resources:
            ekeys = list(e.keys())
            if f"{np}{e.name}{ns}" in ikeys and child_type in ekeys:
                continue_count += 1
            elif child_type in ekeys and kwargs.args.check:
                pcolor.Cyan("\n     * Running in Check Mode")
                pcolor.Cyan(
                    f"       - Skipping {ptitle} {pcategory} Children Retrieval for Org: {org} > {ptitle}:")
                pcolor.Cyan(
                    f"         because `{np}{e.name}{ns}` parent {ptitle} doesn't exists in Intersight.")
            elif child_type in ekeys:
                pcolor.Cyan(
                    f"       - Skipping {ptitle} {pcategory} Children Retrieval for Org: {org} > {ptitle}:")
                pcolor.Cyan(
                    f"         because `{np}{e.name}{ns}` parent {ptitle} doesn't exist in Intersight.")
        # =====================================================================
        # See if Children are already in Intersight
        # =====================================================================
        if continue_count > 0:
            names = []
            for e in kwargs.resources:
                names.append(
                    kwargs.intersight_api[org][self.category][self.type][np + e.name + ns].moid)
            kwargs = configure(
                category=self.category,
                type=f'{self.type}.{child_type}').api_get(
                True,
                names,
                f'{self.type}.{child_type}',
                kwargs)
        return continue_count, kwargs

    # =========================================================================
    # Function - Compare Children Resources API Body to Existing API Results
    # and Append to Bulk List if Differences or No Existing Resource.
    # =========================================================================
    def children_compare_api_body(self, api_body, kwargs):
        org = kwargs.org
        if 'port_channel' in self.type:
            pkey = 'PcId'
        elif 'port_mode' in self.type:
            pkey = 'PortIdStart'
        elif 'port_role' in self.type:
            pkey = 'PortId'
        elif 'provider' in self.type:
            pkey = 'Server'
        elif 'vlans' in self.type:
            pkey = 'VlanId'
        elif 'vsans' in self.type:
            pkey = 'VsanId'
        elif 'ldap_servers' in self.type:
            pkey = 'Server'
        else:
            pkey = 'Name'
        akeys = list(api_body.keys())
        check_flag = getattr(kwargs.args, 'check', False)
        child_type = self.type.split('.')[1]
        child_title = notifications.mod_pol_description(
            child_type.replace('_', ' ').title())
        parent_moid = api_body['Parent']['Moid']
        parent_type = self.type.split('.')[0]
        parent_name = kwargs.intersight_api[org][self.category][parent_type][parent_moid]
        kwargs.uri = kwargs.ezdata[f"intersight.{self.category}.{self.type}"]['x-intersight-uri']
        policy_title = notifications.mod_pol_description(
            ((self.type.replace('_', ' ').replace('.', ' : '))).capitalize())
        if 'Description' in akeys and api_body['Description'] == '':
            api_body['Description'] = f'{api_body["Name"]} {policy_title} {self.category.capitalize()}.'
        parent_title = notifications.mod_pol_description(
            parent_type.replace('_', ' ').title())
        category = self.category.replace(
            'ies', 'y').replace(
            'pools', 'pool').title()
        ptitle = parent_title + ' ' + category
        # If parent_name is not a string the parent policy doesn't exist in Intersight yet;
        # treat the child as new and queue it for creation.
        if not isinstance(parent_name, str):
            if not check_flag:
                kwargs.bulk_list.append(deepcopy(api_body))
            else:
                pcolor.Cyan(
                    f"     * Running Check Mode: Organization: `{org}`; Non-Check mode would create new {ptitle}: (new) - {child_title}: `{api_body[pkey]}`.")
            return kwargs
        child_dict = kwargs.intersight_api[org][self.category][parent_type][parent_name][child_type]
        ikeys = list(child_dict.keys())
        pval = api_body[pkey] if re.search(
            'groups|users|vnic|vhbas|ldap_servers|ldap_groups',
            self.type) else str(
            api_body[pkey])
        if pval in ikeys:
            resource = child_dict[pval].result
            patch_policy = self.compare_body_result(api_body, resource)
            api_body['pmoid'] = child_dict[pval].moid
            pmoid = api_body['pmoid']
            if patch_policy:
                if check_flag:
                    pcolor.Cyan(
                        f"     * Running Check Mode: Organization: `{org}`;")
                    pcolor.Cyan(
                        f"       Non-Check mode would update {ptitle}: `{parent_name}` - {child_title}: `{api_body[pkey]}`.  Moid: `{pmoid}`")
                else:
                    kwargs.bulk_list.append(deepcopy(api_body))
            else:
                pcolor.Cyan(
                    f"     * Skipping Organization: `{org}`; {ptitle}: `{parent_name}` - {child_title}: `{api_body[pkey]}`"
                    f"  Moid: `{pmoid}`.  Intersight Matches Configuration.")
        else:
            if check_flag:
                pcolor.Cyan(
                    f"     * Running Check Mode: Organization: `{org}`; Non-Check mode would create new {ptitle}: "
                    f"`{parent_name}` - {child_title}: `{api_body[pkey]}`.")
            else:
                kwargs.bulk_list.append(deepcopy(api_body))
        return kwargs

    # =========================================================================
    # Function - Assign Children Resources to Parent Resources
    # =========================================================================
    def children_resources(self, child_type, kwargs):
        continue_count, kwargs = self.children_check_parent(child_type, kwargs)
        if continue_count == 0:
            return kwargs
        # =====================================================================
        # See if Children are already in Intersight
        # =====================================================================
        org = kwargs.org
        np, ns = self.name_prefix_suffix(kwargs.org, kwargs)
        names = []
        for e in kwargs.resources:
            names.append(
                kwargs.intersight_api[org][self.category][self.type][np + e.name + ns].moid)
        kwargs = configure(
            category=self.category,
            type=f'{self.type}.{child_type}').api_get(
            True,
            names,
            f'{self.type}.{child_type}',
            kwargs)
        # =====================================================================
        # Create API Body for Sub Items and Compare to Existing API Results.
        # If Differences or No Existing Resource, Append to Bulk List for
        # POST/PATCH.  If No Differences, Skip.
        # =====================================================================
        kwargs.bulk_list = []
        for e in kwargs.resources:
            ekeys = list(e.keys())
            if child_type in ekeys:
                parent_moid = kwargs.intersight_api[org][self.category][self.type][np + e.name + ns].moid
                for item in e[child_type]:
                    item.parent = parent_moid
                    child_np = ''
                    child_ns = ''
                    api_body = configure(
                        category=self.category,
                        type=f'{self.type}.{child_type}').create_api_body(
                        item,
                        child_np,
                        child_ns,
                        kwargs)
                    kwargs = configure(
                        category=self.category,
                        type=f'{self.type}.{child_type}').children_compare_api_body(
                        api_body,
                        kwargs)
        if len(kwargs.bulk_list) > 0:
            kwargs.uri = kwargs.ezdata[f"intersight.{self.category}.{self.type}.{child_type}"]['x-intersight-uri']
            kwargs = configure(
                category=self.category,
                type=f'{self.type}.{child_type}').create_bulk_request(kwargs)
        return kwargs

    # =========================================================================
    # Function - Compare Body Result for Differences
    # =========================================================================
    def compare_body_result(self, api_body, result):
        if 'port_channel' in self.type:
            pkey = 'PcId'
        elif 'port_mode' in self.type:
            pkey = 'PortIdStart'
        elif 'port_role' in self.type:
            pkey = 'PortId'
        elif 'provider' in self.type:
            pkey = 'Server'
        elif 'vlans' in self.type:
            pkey = 'VlanId'
        elif 'vsan' in self.type:
            pkey = 'VsanId'
        else:
            pkey = 'Name'
        expected = deepcopy(api_body)
        current = deepcopy(result)
        differences = []

        def list_sort_key(value, path=''):
            if path.endswith('Tags') and isinstance(value, dict):
                tag_key = str(
                    value.get(
                        'Key',
                        value.get(
                            'key',
                            ''))).strip().lower()
                return (0, 0, tag_key)
            if path.endswith('PolicyBucket') and isinstance(value, dict):
                object_type = str(
                    value.get(
                        'ObjectType',
                        value.get(
                            'objectType',
                            ''))).strip().lower()
                moid = str(
                    value.get(
                        'Moid',
                        value.get(
                            'moid',
                            ''))).strip().lower()
                return (0, 0, object_type, moid)
            if self.type == 'system_qos' and path == 'Classes' and isinstance(
                    value, dict):
                class_name = value.get('Name', value.get('name'))
                if class_name is not None:
                    return (0, 0, str(class_name).strip().lower())
            if isinstance(value, dict):
                priority = value.get('Priority', value.get('priority'))
                if priority is not None:
                    try:
                        pnum = int(priority)
                        return (0, 0, pnum)
                    except (TypeError, ValueError):
                        return (0, 1, str(priority))
            try:
                return (1, 0, json.dumps(value, sort_keys=True))
            except TypeError:
                return (1, 1, str(value))

        def normalize_for_compare(value, path=''):
            if isinstance(value, dict):
                return {
                    k: normalize_for_compare(v, f'{path}.{k}' if path else k)
                    for k, v in value.items()
                }
            if isinstance(value, list):
                normalized_list = [
                    normalize_for_compare(v, f'{path}[{idx}]' if path else f'[{idx}]')
                    for idx, v in enumerate(value)
                ]
                if self.type == 'boot_order' and path == 'BootDevices':
                    return normalized_list
                return sorted(
                    normalized_list,
                    key=lambda v: list_sort_key(
                        v,
                        path))
            return value

        expected = normalize_for_compare(expected)
        current = normalize_for_compare(current)

        def is_sensitive_path(path, key_name=''):
            check = f'{path}.{key_name}'.lower(
            ) if key_name else str(path).lower()
            sensitive_terms = (
                'password',
                'passphrase',
                'private_key',
                'privatekey',
                'existingkey',
                'newkey',
                'secret',
                'token',
            )
            return any(term in check for term in sensitive_terms)

        def sanitize_for_display(value, path='', key_name=''):
            if is_sensitive_path(path, key_name):
                return '__SENSITIVE__'
            return value

        def format_value(value):
            if value == '__SENSITIVE__':
                return 'sensitive'
            try:
                text = json.dumps(value, sort_keys=True)
            except TypeError:
                text = str(value)
            if len(text) > 180:
                return f"{text[:177]}..."
            return text

        def record_diff(
                path,
                expected_value,
                current_value,
                reason='value mismatch',
                key_name=''):
            expected_display = sanitize_for_display(
                expected_value, path, key_name)
            current_display = sanitize_for_display(
                current_value, path, key_name)
            differences.append(
                f"{path or '<root>'}: {reason} | expected={format_value(expected_display)} | current={format_value(current_display)}"
            )

        def values_differ(v1, v2, path='', key_name=''):
            changed = False
            if isinstance(v1, dict):
                if not isinstance(v2, dict):
                    record_diff(path, v1, v2, 'type mismatch', key_name)
                    return True
                for k, v in v1.items():
                    k_path = f'{path}.{k}' if path else k
                    if k not in v2:
                        record_diff(k_path, v, None, 'missing key', k)
                        changed = True
                        continue
                    if values_differ(v, v2[k], k_path, k):
                        changed = True

                return changed

            if isinstance(v1, list):
                if not isinstance(v2, list):
                    record_diff(path, v1, v2, 'type mismatch', key_name)
                    return True
                # Compare tags by Key so extra API-managed tags do not shift
                # index alignment.
                if path.endswith('Tags') and all(
                        isinstance(item, dict) for item in v1):
                    v2_by_key = {str(tag.get('Key', tag.get('key'))): tag for tag in v2 if isinstance(
                        tag, dict) and (tag.get('Key') is not None or tag.get('key') is not None)}
                    for tag in v1:
                        tkey = str(tag.get('Key', tag.get('key')))
                        tpath = f'{path}[Key={tkey}]'
                        if tkey not in v2_by_key:
                            record_diff(
                                tpath, tag, None, 'missing tag key', 'Key')
                            changed = True
                            continue
                        if values_differ(tag, v2_by_key[tkey], tpath, 'Key'):
                            changed = True
                    return changed
                if len(v2) < len(v1):
                    record_diff(
                        path, v1, v2, 'list length/type mismatch', key_name)
                    changed = True
                for idx, item in enumerate(v1):
                    if idx >= len(v2):
                        break
                    idx_path = f'{path}[{idx}]' if path else f'[{idx}]'
                    if values_differ(item, v2[idx], idx_path, key_name):
                        changed = True
                return changed

            if v1 != v2:
                record_diff(path, v1, v2, 'value mismatch', key_name)
                return True
            return False

        changed = values_differ(expected, current)
        if changed and len(differences) > 0:
            pcolor.Yellow(
                f'     - Differences found for `{self.type}` -> name: {api_body[pkey]} ({len(differences)}):')
            max_show = 1024
            for diff in differences[:max_show]:
                pcolor.Yellow(f'       * {diff}')
            if len(differences) > max_show:
                pcolor.Yellow(
                    f'       * ... {len(differences) - max_show} additional differences omitted')
        return changed

    # =========================================================================
    # Function - If Modified, Patch the Resource via the Intersight API
    # =========================================================================
    def compare_resources_to_api(self, api_body, ptitle, kwargs):
        category = self.category.replace('_', ' ').title()
        kwargs.uri = kwargs.ezdata[f"intersight.{self.category}.{self.type}"]['x-intersight-uri']
        check_flag = getattr(kwargs.args, 'check', False)
        akeys = list(api_body.keys())
        if 'Description' in akeys and api_body['Description'] == '':
            word = self.category
            api_body['Description'] = f'{api_body["Name"]} {ptitle} {re.sub(r"s$", "", DESCRIPTION_WORD_MAP.get(word, word))}.'
        if api_body['Name'] in kwargs.intersight_api[kwargs.org][self.category][self.type]:
            intersight_api = kwargs.intersight_api[kwargs.org][self.category][self.type][api_body['Name']]
            patch_resource = self.compare_body_result(
                api_body, intersight_api.result)
            api_body['pmoid'] = intersight_api.moid
            if patch_resource:
                if check_flag:
                    pcolor.Cyan(
                        f"     * Running Check Mode: Organization: `{kwargs.org}`; Non-Check mode would update {category} -> {ptitle}: `{api_body['Name']}`."
                        f"  Moid: `{api_body['pmoid']}`")
                else:
                    kwargs.bulk_list.append(deepcopy(api_body))
                    kwargs.pmoids[api_body['Name']].moid = api_body['pmoid']
            else:
                pcolor.Cyan(
                    f"     * Skipping Organization: `{kwargs.org}`; {category} -> {ptitle}: `{api_body['Name']}` - Moid: `{api_body['pmoid']}`."
                    f"  Intersight Matches Configuration.")
        else:
            if check_flag:
                pcolor.Cyan(
                    f"     * Running Check Mode: Organization: `{kwargs.org}`; Non-Check mode would create new {category} -> {ptitle}: `{api_body['Name']}`.")
            else:
                kwargs.bulk_list.append(deepcopy(api_body))
        return kwargs

    # =========================================================================
    # Function - Compare Intersight API to IMM Dictionary `configure`
    # =========================================================================
    def configure(self, kwargs):
        # =====================================================================
        # Send Begin Notification and Load Variables
        # =====================================================================
        ptitle = notifications.mod_pol_description(
            (self.type.replace('_', ' ').title()))
        notifications.section_begin_org(
            kwargs.org, ptitle, self.category.title())
        pcolor.LightGray('')
        rdict = deepcopy(
            kwargs.imm_dict.orgs[kwargs.org][self.category][self.type])
        if self.type == 'port':
            reconcile_resources = list({v.names[0]: v for v in rdict}.values())
        elif self.type == 'firmware_authenticate':
            kwargs = self.firmware_authenticate(kwargs)
            notifications.section_end_org(
                kwargs.org, ptitle, self.category.title())
            return kwargs
        elif self.category == 'templates' and not re.search('(vnic|vhba)_template', self.type):
            reconcile_resources = list({v.name: v for v in rdict if v.get(
                'create_template', False) is True}.values())
        elif self.category == 'profiles' and re.search('(chassis|server)', self.type):
            reconcile_resources = list(
                {t.name: p | t for p in rdict for t in p.targets}.values())
            for v in reconcile_resources:
                v.pop('targets', None)
            # Remove any C885A Server Profiles as they are not supported in Intersight and will cause unnecessary API calls
            #  and noise in the output.
            if self.category == 'profiles' and self.type == 'server':
                reconcile_resources = [
                    e for e in reconcile_resources if e.get('server_family') != 'UCSC885A']
        else:
            reconcile_resources = list({v.name: v for v in rdict}.values())
        # =====================================================================
        # Get Existing Resources
        # =====================================================================
        np, ns = self.name_prefix_suffix(kwargs.org, kwargs)
        names = []
        for e in reconcile_resources:
            if self.type == 'port':
                names.extend(
                    [f'{np}{e.names[x]}{ns}' for x in range(0, len(e.names))])
            else:
                names.append(f"{np}{e['name']}{ns}")
        kwargs = self.api_get(True, names, self.type, kwargs)
        # =====================================================================
        # Validate the Sub Resources are defined or get Moids
        # =====================================================================
        if self.category == 'templates' and not re.search(
                '(vnic|vhba)_template', self.type):
            reconcile_resources = list({v.name: v for v in rdict}.values())
        regex1 = re.compile(
            r'id_mapping|imc_access|ip|iscsi_boot|(l|s)an_connectivity|organizations|port|resource|(vhba|vnic)_template|vlan',
            re.IGNORECASE)
        regex2 = re.compile(
            r'(chassis|domain|server|unified_edge)',
            re.IGNORECASE)
        regcomb = re.compile(
            '|'.join([regex1.pattern, regex2.pattern]), re.IGNORECASE)
        if re.search(regcomb, self.type):
            kwargs.cp = DotMap()
            updated_resources = []
            for e in reconcile_resources:
                e, kwargs = self.existing_check(e, kwargs)
                updated_resources.append(e)
            reconcile_resources = updated_resources
            if not re.search('id_mapping', self.type):
                for e in list(kwargs.cp.keys()):
                    if len(kwargs.cp[e].names) > 0:
                        names = list(
                            numpy.unique(
                                numpy.array(
                                    kwargs.cp[e].names)))
                        category = kwargs.cp[e].get('category', self.category)
                        kwargs = configure(
                            category=category, type=e).api_get(
                            False, names, e, kwargs)
        if re.search('profiles|templates', self.category):
            kwargs.policies = DotMap()
            kwargs.pools = DotMap()
            for key, value in kwargs.intersight_api.items():
                for k, v in value.policies.items():
                    kwargs.policies.setdefault(k, DotMap())
                    for a, b in v.items():
                        if hasattr(b, 'moid'):
                            kwargs.policies[k][b.moid] = DotMap(
                                name=a, organization=key)
                for k, v in value.pools.items():
                    kwargs.pools.setdefault(k, DotMap())
                    for a, b in v.items():
                        if hasattr(b, 'moid'):
                            kwargs.pools[k][b.moid] = DotMap(
                                name=a, organization=key)
            if self.category == 'templates':
                for e in reconcile_resources:
                    kwargs.imm_templates[kwargs.org].templates[self.type][f'{np}{e.name}{ns}'] = e
                reconcile_resources = list({v.name: v for v in reconcile_resources if v.get(
                    'create_template', False) is True}.values())
        # =====================================================================
        # If Domain or Unified Edge or Chassis/Server Profiles process all resources in function
        # =====================================================================
        kwargs.resources = deepcopy(reconcile_resources)
        if self.category == 'profiles' and re.search(
                r'(chassis|server)', self.type):
            kwargs = getattr(self, f'profiles_{self.type}')(kwargs)
            return kwargs
        elif re.search(r'(domain|unified_edge)', self.type):
            kwargs = getattr(self, f'{self.category}_{self.type}')(kwargs)
            return kwargs
        # =====================================================================
        # Else Loop through Resource Items
        # =====================================================================
        kwargs.bulk_list = []
        for item in reconcile_resources:
            if self.type == 'port':
                for x in range(0, len(item.names)):
                    # Construct api_body Payload
                    item.name = item.names[x]
                    api_body = self.create_api_body(item, np, ns, kwargs)
                    kwargs = self.compare_resources_to_api(
                        api_body, ptitle, kwargs)
            else:
                # Construct api_body Payload
                api_body = self.create_api_body(item, np, ns, kwargs)
                kwargs = self.compare_resources_to_api(
                    api_body, ptitle, kwargs)
        # =====================================================================
        # POST Bulk Request if List > 0
        # =====================================================================
        if len(kwargs.bulk_list) > 0:
            kwargs.uri = kwargs.ezdata[f"intersight.{self.category}.{self.type}"]['x-intersight-uri']
            kwargs = self.create_bulk_request(kwargs)
        # =====================================================================
        # Loop Thru Sub-Items
        # =====================================================================
        kwargs.resources = deepcopy(reconcile_resources)
        if 'port' == self.type:
            kwargs = self.policies_port_children(kwargs)
        elif 'snmp' == self.type:
            kwargs = self.policies_snmp(kwargs)
        elif re.search(r'^ldap|local_user||(l|s)an_connectivity|storage|v(l|s)an$', self.type):
            sub_list = [
                'lan_connectivity.vnics',
                'lan_connectivity.vnics_from_template',
                'ldap.ldap_groups',
                'ldap.ldap_servers',
                'local_user.users',
                'san_connectivity.vhbas',
                'san_connectivity.vhbas_from_template',
                'storage.drive_groups',
                'vlan.vlans',
                'vsan.vsans']
            for e in sub_list:
                a, b = e.split('.')
                if a == self.type:
                    scount = 0
                    for i in kwargs.resources:
                        ikeys = list(i.keys())
                        if b in ikeys:
                            scount += 1
                    if scount > 0:
                        kwargs = getattr(self, f'policies_{a}_{b}')(kwargs)
        # =====================================================================
        # Send End Notification and return kwargs
        # =====================================================================
        notifications.section_end_org(
            kwargs.org, ptitle, self.category.title())
        return kwargs

    # =========================================================================
    # Function - Create API Request Body
    # =========================================================================
    def create_api_body(self, item, np, ns, kwargs):
        regex = re.compile(
            r'bios|certificate_management|drive_security|(ethernet|fibre_channel)_adapter|storage|system_qos')
        if re.fullmatch(regex, self.type):
            item = getattr(self, f'policies_{self.type}')(item, kwargs)
        elif self.category == 'templates' and re.search('(chassis|server)', self.type):
            item = getattr(self, f'templates_{self.type}')(item, kwargs)
        elif self.category == 'profiles' and re.search('(chassis|server)', self.type):
            item = getattr(
                self, 'profiles_templates_create_policy_bucket')(
                item, kwargs)

        item = self.merge_tags(item, kwargs)

        template_dir = os.path.join(
            os.path.dirname(
                kwargs.script_path),
            'templates',
            'intersight',
            f'{self.category}')
        template_name = f'{self.type}.json.j2'
        template_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_dir),
            autoescape=False)

        render_item = item.toDict() if hasattr(item, 'toDict') else item
        rendered = template_env.get_template(template_name).render(
            item=render_item,
            isight=kwargs.intersight_api,
            name_prefix=np,
            name_suffix=ns,
            object_map=kwargs.intersight_object_map,
            organization=kwargs.org,
            org_moids=kwargs.org_moids,
            rsg_moids=kwargs.rsg_moids,
            sensitive_vars=kwargs.sensitive_vars
        )
        try:
            api_body = json.loads(rendered)
        except json.JSONDecodeError as exc:
            policy_title = notifications.mod_pol_description(
                (self.type.replace('_', ' ')).capitalize())
            pcolor.Red(
                f'!!! ERROR !!! Failed to parse rendered JSON for {policy_title} template '
                f'`{template_name}` (line {exc.lineno}, column {exc.colno}).')
            start = max(1, exc.lineno - 2)
            end = min(len(rendered.splitlines()), exc.lineno + 2)
            for line_no in range(start, end + 1):
                marker = '>>' if line_no == exc.lineno else '  '
                pcolor.Yellow(
                    f'{marker} {line_no:4}: {rendered.splitlines()[line_no - 1]}')
            raise
        if not isinstance(api_body, dict):
            policy_title = notifications.mod_pol_description(
                (self.type.replace('_', ' ')).capitalize())
            pcolor.Red(
                f'!!! ERROR !!! {policy_title} template did not render to a dictionary payload.')
            raise ValueError(
                f'{policy_title} template did not render to a dictionary payload')
        return api_body

    # =========================================================================
    # Function - Create Bulk API Request Body
    # =========================================================================
    def create_bulk_request(self, kwargs):
        def post_to_api(kwargs):
            kwargs = kwargs | DotMap(method='post', uri='bulk/Requests')
            kwargs = api(
                category=self.category,
                type='bulk_request').calls(kwargs)
            return kwargs

        def loop_thru_lists(kwargs):
            if len(kwargs.api_body['Requests']) > 99:
                requests_list = deepcopy(kwargs.api_body['Requests'])
                chunked_list = list()
                chunk_size = 100
                for i in range(0, len(requests_list), chunk_size):
                    chunked_list.append(requests_list[i:i + chunk_size])
                for i in chunked_list:
                    kwargs.api_body['Requests'] = i
                    kwargs = post_to_api(kwargs)
            else:
                kwargs = post_to_api(kwargs)
            return kwargs
        # =====================================================================
        # Create API Body for Bulk Request
        # =====================================================================
        patch_list = []
        post_list = []
        for e in kwargs.bulk_list:
            if e.get('Parent'):
                e.pop('Parent')
            if e.get('pmoid'):
                tmoid = e['pmoid']
                e.pop('pmoid')
                patch_list.append({'Body': e,
                                   'ClassId': 'bulk.RestSubRequest',
                                   'ObjectType': 'bulk.RestSubRequest',
                                   'TargetMoid': tmoid,
                                   'Uri': f'/v1/{kwargs.uri}',
                                   'Verb': 'PATCH'})
            else:
                post_list.append({'Body': e,
                                  'ClassId': 'bulk.RestSubRequest',
                                  'ObjectType': 'bulk.RestSubRequest',
                                  'Uri': f'/v1/{kwargs.uri}',
                                  'Verb': 'POST'})
        if len(patch_list) > 0:
            kwargs.api_body = {'Requests': patch_list}
            kwargs = loop_thru_lists(kwargs)
        if len(post_list) > 0:
            kwargs.api_body = {'Requests': post_list}
            kwargs = loop_thru_lists(kwargs)
        return kwargs

    # =========================================================================
    # Function: Deep Merge Dictionaries
    # =========================================================================
    def deep_merge_dicts(self, dest, src):
        for key, value in src.items():
            if key in dest and isinstance(
                    dest[key],
                    dict) and isinstance(
                    value,
                    dict):
                self.deep_merge_dicts(dest[key], value)
            else:
                dest[key] = deepcopy(value)
        return dest

    # =========================================================================
    # Function - Check if Org is in Resource Name and Split
    # =========================================================================
    def determine_resource_organization(
            self,
            add_prefix_suffix=True,
            resource=None,
            kwargs=None):
        if '/' in resource:
            org, rname = resource.split('/')
        else:
            org = kwargs.org
            rname = resource
        if add_prefix_suffix:
            np, ns = self.name_prefix_suffix(org, kwargs)
            rname = np + rname + ns
        return org, rname

    # =========================================================================
    # Function - Check if Sub Policies exist in the Intersight API
    # =========================================================================
    def existing_check(self, item, kwargs):
        # =====================================================================
        # Constants
        # =====================================================================
        RESOURCE_PATTERN = r'_polic(ies|y)|_pool(s)?|(vhba|vnic)_template$'
        IP_BLOCK_TYPES = ['ipv4_blocks', 'ipv6_blocks']
        RTYPE_ADJUSTMENTS = {
            'band_ip': 'ip',
            'primary_target': 'iscsi_static_target',
            'secondary_target': 'iscsi_static_target'
        }
        # =====================================================================
        # Helper Functions
        # =====================================================================

        def extract_ptype(key_str):
            """Extract policy type from key by removing common suffixes and prefixes."""
            replacements = [
                ('_policies', ''), ('_address_pools', ''), ('_pools', ''),
                ('_policy', ''), ('_address', ''), ('initiator_', '')
            ]
            rtype = key_str
            for old, new in replacements:
                rtype = rtype.replace(old, new)
            rtype = re.sub(r'_pool$', '', rtype)
            return rtype

        def adjust_rtype(rtype):
            """Apply rtype adjustments based on pattern matching."""
            for pattern, adjusted_type in RTYPE_ADJUSTMENTS.items():
                if re.search(pattern, rtype):
                    return adjusted_type
            return rtype

        def get_resource_category(key):
            """Determine if resource is pool, template, or policy based on key."""
            if key == 'pool_name' or re.search(r'_pool[s]?$', key):
                return 'pools'
            elif 'template' in key:
                return 'templates'
            else:
                return 'policies'

        def update_item_with_adjusted_name(
                item, key, old_name, new_name, is_ip_type=False):
            """Update item dictionary with adjusted resource name. Mutates item in place."""
            CHILD_CONTAINER_KEYS = [
                'vhbas',
                'vhbas_from_template',
                'vnics',
                'vnics_from_template',
                'port_channel_appliances',
                'port_channel_ethernet_uplinks',
                'port_channel_fcoe_uplinks',
                'port_role_appliances',
                'port_role_ethernet_uplinks',
                'port_role_fcoe_uplinks',
            ]
            if is_ip_type:
                for ip_block_type in IP_BLOCK_TYPES:
                    if ip_block_type in item and isinstance(
                            item[ip_block_type], list):
                        for x in range(len(item[ip_block_type])):
                            if item[ip_block_type][x].get(key) == old_name:
                                item[ip_block_type][x][key] = new_name
            elif self.type == 'server' and key == 'pool_name':
                for reservation in item.get('reservations') or []:
                    if isinstance(reservation, dict) and reservation.get(
                            'pool_name') == old_name:
                        reservation['pool_name'] = new_name
            elif key in item:
                if isinstance(item[key], list):
                    indx = next(
                        (i for i, d in enumerate(
                            item[key]) if d == old_name), None)
                    if indx is not None:
                        item[key][indx] = new_name
                else:
                    item[key] = new_name
            else:
                for container_key in CHILD_CONTAINER_KEYS:
                    if container_key in item and isinstance(
                            item[container_key], list):
                        for child in item[container_key]:
                            if key in child:
                                if isinstance(child[key], list):
                                    indx = next(
                                        (i for i, d in enumerate(
                                            child[key]) if d == old_name), None)
                                    if indx is not None:
                                        child[key][indx] = new_name
                                elif child[key] == old_name:
                                    child[key] = new_name

        def resource_list(k, rname, rtype, item, kwargs):
            """Validate resource existence and register missing resources. Mutates item and kwargs."""
            r = get_resource_category(k)
            org, new_rname = configure(
                category=r, type=rtype).determine_resource_organization(
                add_prefix_suffix=True, resource=rname, kwargs=kwargs)
            current_name = rname if '/' in rname else f'{org}/{rname}'
            target_name = f'{org}/{new_rname}'
            if current_name != target_name:
                pcolor.Yellow(
                    f'     * Adjusted {rtype} name from `{rname}` to `{target_name}` based on org `{org}` in resource `{k}`.')
                update_item_with_adjusted_name(
                    item, k, rname, target_name, is_ip_type=self.type == 'ip')
            ckeys = list(kwargs.cp)
            if rtype not in ckeys:
                kwargs.cp[rtype].names = []
                kwargs.cp[rtype].category = r
            rkeys = list(kwargs.intersight_api[org][r][rtype].keys())
            if 'template' in k:
                kwargs.cp[rtype].names.append(target_name)
            elif new_rname not in rkeys:
                kwargs.cp[rtype].names.append(target_name)
            return item, kwargs

        # =====================================================================
        # Handle template reference for chassis/domain/server/unified_edge profiles
        # =====================================================================
        if re.search(r'^(chassis|domain|server|unified_edge)', self.type):
            template_key = next(
                (k for k in item if template_regex.match(k)), None)
            if template_key and item.get(template_key):
                m = re.search(r'ucs_(server|chassis)', template_key)
                if m:
                    rtype = f'{m.group(1)}'
                    item, kwargs = resource_list(
                        template_key, item[template_key], rtype, item, kwargs)
        # =====================================================================
        # Process IP Type Specifically
        # =====================================================================
        if self.type == 'ip':
            for e in IP_BLOCK_TYPES:
                if e in item and isinstance(item[e], list):
                    for x in range(len(item[e])):
                        if 'id_mapping_policy' in item[e][x]:
                            item, kwargs = resource_list(
                                'id_mapping_policy', item[e][x]['id_mapping_policy'], 'id_mapping', item, kwargs)
        elif self.type == 'id_mapping':
            if 'organizations' in item:
                okeys = list(
                    kwargs.intersight_api[kwargs.org]['system']['organizations'].keys())
                names = [e for e in item.organizations if e in okeys]
                if len(names) > 0:
                    kwargs.orgs = list(
                        numpy.unique(
                            numpy.array(
                                kwargs.orgs +
                                names)))
                    kwargs = api(
                        category='system',
                        type='organizations').organizations(kwargs)
            if 'resource_groups' in item:
                rkeys = list(kwargs.rsg_moids.keys())
                names = [e for e in item.resource_groups if e in rkeys]
                if len(names) > 0:
                    kwargs.resource_groups = list(numpy.unique(
                        numpy.array(kwargs.resource_groups + names)))
                    kwargs = api(category='system',
                                 type='resource_groups').organizations(kwargs)
        # =====================================================================
        # Process LAN Connectivity Type - Extract Sub-Resources from vNICs
        # =====================================================================
        elif self.type == 'lan_connectivity':
            vnic_sub_map = {
                'ethernet_adapter_policy': 'ethernet_adapter_policy',
                'ethernet_adapter_policies': 'ethernet_adapter_policy',
                'ethernet_network_policy': 'ethernet_network_policy',
                'ethernet_network_policies': 'ethernet_network_policy',
                'ethernet_network_control_policy': 'ethernet_network_control_policy',
                'ethernet_network_control_policies': 'ethernet_network_control_policy',
                'ethernet_network_group_policies': 'ethernet_network_group_policy',
                'ethernet_qos_policy': 'ethernet_qos_policy',
                'ethernet_qos_policies': 'ethernet_qos_policy',
                'mac_address_pool': 'mac',
                'mac_address_pools': 'mac'}
            for vnic_container_key in ['vnics', 'vnics_from_template']:
                if vnic_container_key in item:
                    for vnic_item in item[vnic_container_key]:
                        for sub_key, rtype in vnic_sub_map.items():
                            if sub_key in vnic_item and vnic_item[sub_key]:
                                sub_value = vnic_item[sub_key]
                                config_key = extract_ptype(
                                    rtype) if sub_key != 'mac_address_pool' else rtype
                                if isinstance(sub_value, list):
                                    for sub_resource in sub_value:
                                        item, kwargs = resource_list(
                                            sub_key, sub_resource, config_key, item, kwargs)
                                else:
                                    item, kwargs = resource_list(
                                        sub_key, sub_value, config_key, item, kwargs)
                        # For vnics_from_template, also extract vnic_template
                        # reference
                        if vnic_container_key == 'vnics_from_template' and 'vnic_template' in vnic_item and vnic_item[
                                'vnic_template']:
                            item, kwargs = resource_list(
                                'vnic_template', vnic_item['vnic_template'], 'vnic_template', item, kwargs)
        # =====================================================================
        # Process Port Type Specifically - Extract Sub-Resources
        # =====================================================================
        elif self.type == 'port':
            # Map field names (as they appear in data) to resource types
            # Config key will be automatically extracted via extract_ptype
            port_sub_map = {
                'ethernet_network_group_policies': 'ethernet_network_group_policy',
                'ethernet_network_group_policy': 'ethernet_network_group_policy',
                'ethernet_network_control_policy': 'ethernet_network_control_policy',
                'flow_control_policy': 'flow_control_policy',
                'link_aggregation_policy': 'link_aggregation_policy',
                'link_control_policy': 'link_control_policy',
                'mac_sec_policy': 'mac_sec_policy'}
            for port_type_key in [
                'port_channel_appliances',
                'port_channel_ethernet_uplinks',
                'port_channel_fcoe_uplinks',
                'port_role_appliances',
                'port_role_ethernet_uplinks',
                    'port_role_fcoe_uplinks']:
                if port_type_key in item:
                    for policy_item in item[port_type_key]:
                        for sub_key, rtype in port_sub_map.items():
                            if sub_key in policy_item and policy_item[sub_key]:
                                sub_value = policy_item[sub_key]
                                # Extract config key from resource type using
                                # extract_ptype
                                config_key = extract_ptype(rtype)
                                if isinstance(sub_value, list):
                                    for sub_resource in sub_value:
                                        item, kwargs = resource_list(
                                            sub_key, sub_resource, config_key, item, kwargs)
                                else:
                                    item, kwargs = resource_list(
                                        sub_key, sub_value, config_key, item, kwargs)
        # =====================================================================
        # Process SAN Connectivity Type - Extract Sub-Resources from vHBAs
        # =====================================================================
        elif self.type == 'san_connectivity':
            # Policy-level pool reference (separate from child vHBA pools).
            if 'wwnn_pool' in item and item['wwnn_pool']:
                item, kwargs = resource_list(
                    'wwnn_pool', item['wwnn_pool'], 'wwnn', item, kwargs)
            elif 'wwnn_pools' in item and item['wwnn_pools']:
                wwnn_value = item['wwnn_pools']
                if isinstance(wwnn_value, list):
                    for pool_name in wwnn_value:
                        item, kwargs = resource_list(
                            'wwnn_pools', pool_name, 'wwnn', item, kwargs)
                else:
                    item, kwargs = resource_list(
                        'wwnn_pools', wwnn_value, 'wwnn', item, kwargs)

            vhba_sub_map = {
                'fibre_channel_adapter_policy': 'fibre_channel_adapter_policy',
                'fibre_channel_network_policy': 'fibre_channel_network_policy',
                'fibre_channel_network_policies': 'fibre_channel_network_policy',
                'fibre_channel_qos_policy': 'fibre_channel_qos_policy',
                'wwpn_pool': 'wwpn',
                'wwpn_pools': 'wwpn'}
            for vhba_container_key in ['vhbas', 'vhbas_from_template']:
                if vhba_container_key in item:
                    for vhba_item in item[vhba_container_key]:
                        for sub_key, rtype in vhba_sub_map.items():
                            if sub_key in vhba_item and vhba_item[sub_key]:
                                sub_value = vhba_item[sub_key]
                                config_key = extract_ptype(rtype) if sub_key not in [
                                    'wwpn_pool', 'wwpn_pools'] else rtype
                                if isinstance(sub_value, list):
                                    for sub_resource in sub_value:
                                        item, kwargs = resource_list(
                                            sub_key, sub_resource, config_key, item, kwargs)
                                else:
                                    item, kwargs = resource_list(
                                        sub_key, sub_value, config_key, item, kwargs)
                        # For vhbas_from_template, also extract vhba_template
                        # reference
                        if vhba_container_key == 'vhbas_from_template' and 'vhba_template' in vhba_item and vhba_item[
                                'vhba_template']:
                            item, kwargs = resource_list(
                                'vhba_template', vhba_item['vhba_template'], 'vhba_template', item, kwargs)
        # =====================================================================
        # Process Server Type Specifically - Extract Reservation Pools from Targets
        # =====================================================================
        elif self.type == 'server':
            reservation_identity_types = {
                'ip', 'iqn', 'mac', 'uuid', 'wwpn', 'wwnn'}
            for reservation in item.get('reservations') or []:
                if not isinstance(reservation, dict):
                    continue
                pool_name = reservation.get('pool_name')
                identity_type = reservation.get('identity_type')
                if pool_name and identity_type:
                    pool_type = str(identity_type).lower()
                    if pool_type in reservation_identity_types:
                        item, kwargs = resource_list(
                            'pool_name', pool_name, pool_type, item, kwargs)
        # =====================================================================
        # Process All Other Types
        # =====================================================================
        else:
            for k, v in item.items():
                if re.search(RESOURCE_PATTERN, k):
                    rtype = extract_ptype(k)
                    rtype = adjust_rtype(rtype)
                    if isinstance(v, list):
                        for e in v:
                            item, kwargs = resource_list(
                                k, e, rtype, item, kwargs)
                    else:
                        item, kwargs = resource_list(k, v, rtype, item, kwargs)
                elif re.search('vmq|usnic', k):
                    vkeys = list(v.keys())
                    if 'vmmq_adapter_policy' in vkeys and len(
                            v.get('vmmq_adapter_policy', '')) > 0:
                        item, kwargs = resource_list(
                            'ethernet_adapter_policy', v['vmmq_adapter_policy'], 'ethernet_adapter', item, kwargs)
                    elif 'usnic_adapter_policy' in vkeys and len(v.get('usnic_adapter_policy', '')) > 0:
                        item, kwargs = resource_list(
                            'ethernet_adapter_policy', v['usnic_adapter_policy'], 'ethernet_adapter', item, kwargs)
        return item, kwargs

    # =========================================================================
    # Function - Merge Tags from Global Settings, Item, and Script
    # =========================================================================
    def merge_tags(self, item, kwargs):
        def as_tag_list(value):
            if value is None:
                return []
            if isinstance(value, list):
                return value
            if isinstance(value, DotMap):
                return [value]
            if isinstance(value, dict):
                return [value]
            return []

        gs = kwargs.intersight.get(
            'global_settings') if kwargs.get('intersight') else None
        global_tags = as_tag_list(gs.get('tags')) if gs else []
        if isinstance(item, dict):
            item_tags = as_tag_list(item.get('tags'))
        else:
            item_tags = as_tag_list(
                item.get('tags')) if hasattr(
                item,
                'get') else as_tag_list(
                getattr(
                    item,
                    'tags',
                    None))

        include_script_tags = True
        if gs and gs.get('include_script_tags') is False:
            include_script_tags = False
        script_tags = as_tag_list(
            kwargs.ez_tags) if include_script_tags and kwargs.get('ez_tags') else []

        merged_tags = []
        seen_tags = set()
        for tag in global_tags + item_tags + script_tags:
            try:
                tag_obj = tag.toDict() if hasattr(tag, 'toDict') else deepcopy(tag)
            except Exception:  # pylint: disable=broad-exception-caught
                tag_obj = deepcopy(tag)
            if isinstance(tag_obj, DotMap):
                tag_obj = tag_obj.toDict()
            if not isinstance(tag_obj, dict):
                continue
            tag_key = json.dumps(tag_obj, sort_keys=True, default=str)
            if tag_key in seen_tags:
                continue
            seen_tags.add(tag_key)
            merged_tags.append(tag_obj)

        if isinstance(item, dict):
            item['tags'] = merged_tags
        else:
            item.tags = merged_tags

        # Keep a predictable shape for template rendering when no tags are
        # defined.
        if isinstance(item, dict) and item.get('tags') is None:
            item['tags'] = []
        elif not isinstance(item, dict) and getattr(item, 'tags', None) is None:
            item.tags = []
        return item

    # =========================================================================
    # Function - Add Prefix / Suffix to Resource Name
    # =========================================================================
    def name_prefix_suffix(self, org, kwargs):
        args = DotMap(name_prefix='', name_suffix='')
        ckeys = list(kwargs.imm_dict.orgs[org][self.category].keys())
        for e in ['name_prefix', 'name_suffix']:
            if e in ckeys:
                nkeys = list(
                    kwargs.imm_dict.orgs[org][self.category][e].keys())
                if self.type in nkeys:
                    if len(kwargs.imm_dict.orgs[org]
                           [self.category][e][self.type]) > 0:
                        args[e] = kwargs.imm_dict.orgs[org][self.category][e][self.type]
                if args[e] == '':
                    if 'default' in nkeys:
                        if len(
                                kwargs.imm_dict.orgs[org][self.category][e]['default']) > 0:
                            args[e] = kwargs.imm_dict.orgs[org][self.category][e]['default']
        return args.name_prefix, args.name_suffix

    # =========================================================================
    # Function - BIOS Policy Updates
    # =========================================================================
    def policies_bios(self, item, kwargs):
        ikeys = item.keys()
        if 'bios_template' in ikeys:
            template_name = item.bios_template
            templates = kwargs.ezdata[f'intersight.{self.category}.{self.type}'].allOf[1].properties.bios_template.enum
            btemplates = kwargs.ezdata[f'intersight.{self.category}.{self.type}.templates'].properties
            if template_name not in templates:
                pcolor.Red(
                    f'!!! ERROR !!! Bios Template "{template_name}" was not found in "intersight.{self.category}.{self.type}.templates".')
                pcolor.Red(
                    f'Available templates are: {", ".join(sorted(list(templates.keys())))}')
                raise ValueError(
                    f'BIOS template "{template_name}" was not found in "intersight.{self.category}.{self.type}.templates"')
            btemplate = btemplates[re.sub(
                r'-tpm$', '', item.bios_template, flags=re.IGNORECASE)]
            if '-tpm' in (item.bios_template).lower():
                item = btemplate | btemplates.tpm | item
            else:
                item = btemplate | item
        return item

    # =========================================================================
    # Function - Certificate Policy Updates
    # =========================================================================
    def policies_certificate_management(self, item, kwargs):
        ikeys = item.keys()
        if 'certificates' in ikeys:
            for x in range(0, len(item.certificates)):
                xkeys = list(item.certificates[x].keys())
                if 'certificate_file' in xkeys:
                    cert_content = self.cert_file_check(
                        expected_type='certificate',
                        file_path=item.certificates[x]['certificate_file'],
                        item=item)
                    item.certificates[x]['certificate_file'] = cert_content
                if 'private_key_file' in xkeys and item.certificates[x].get(
                        'private_key_file'):
                    key_content = self.cert_file_check(
                        expected_type='private_key',
                        file_path=item.certificates[x]['private_key_file'],
                        item=item)
                    item.certificates[x]['private_key_file'] = key_content
        return item

    # =========================================================================
    # Function - Drive Security Policy Updates
    # =========================================================================
    def policies_drive_security(self, item, kwargs):
        ikeys = item.keys()
        if 'remote_key_management' in ikeys:
            rkeys = list(item.remote_key_management.keys())
            if 'server_public_root_ca_certificate' in rkeys and len(
                    item.remote_key_management.get('server_public_root_ca_certificate', '')) > 0:
                cert_content = self.cert_file_check(
                    expected_type='certificate',
                    file_path=item.remote_key_management['server_public_root_ca_certificate'],
                    item=item)
                item.remote_key_management['server_public_root_ca_certificate'] = cert_content
        return item

    # =========================================================================
    # Function - Ethernet Adapter Policy Updates
    # =========================================================================
    def policies_ethernet_adapter(self, item, kwargs):
        item = self.policies_ethernet_fc_adapter(item, kwargs)
        return item

    # =========================================================================
    # Function - Ethernet / FC Adapter Policy Updates
    # =========================================================================
    def policies_ethernet_fc_adapter(self, item, kwargs):
        ikeys = list(item.keys())
        ptitle = notifications.mod_pol_description(
            (self.type.replace('_', ' ').title()))
        if 'adapter_template' in ikeys:
            templates = kwargs.ezdata[f'intersight.{self.category}.{self.type}.templates'].properties
            template_name = item.adapter_template
            if template_name not in templates:
                pcolor.Red(
                    f'!!! ERROR !!! {ptitle} Template "{template_name}" was not found in "intersight.{self.category}.{self.type}.templates".')
                pcolor.Red(
                    f'Available templates are: {", ".join(sorted(list(templates.keys())))}')
                raise ValueError(
                    f'{ptitle} template "{template_name}" was not found in "intersight.{self.category}.{self.type}.templates"')
            merged = deepcopy(templates[template_name].toDict())
            merged = self.deep_merge_dicts(merged, item.toDict())
            item = DotMap(merged)
        return item

    # =========================================================================
    # Function - Fibre-Channel Adapter Policy Updates
    # =========================================================================
    def policies_fibre_channel_adapter(self, item, kwargs):
        item = self.policies_ethernet_fc_adapter(item, kwargs)
        return item

    # =========================================================================
    # Function - Validate CCO Authorization
    # =========================================================================
    def policies_firmware_authenticate(self, kwargs):
        for e in ['cco_password', 'cco_user']:
            if os.environ.get(e) is None:
                kwargs.sensitive_var = e
                kwargs = shared_functions.sensitive_var_value(kwargs)
                os.environ[e] = kwargs.value
        api_body = {
            'ObjectType': 'softwarerepository.Authorization',
            'Password': os.environ['cco_password'],
            'RepositoryType': 'Cisco',
            'UserId': os.environ['cco_user']}
        kwargs = kwargs | DotMap(
            api_body=api_body,
            method='post',
            uri='softwarerepository/Authorizations')
        kwargs = api('firmware_authorization').calls(kwargs)
        return kwargs

    # =========================================================================
    # Function - Configure -> Policies -> System QoS Policy Updates
    # =========================================================================
    def policies_system_qos(self, item, kwargs):
        if not isinstance(item.target_platform, str):
            item.target_platform = "UCS Domain"
        if not isinstance(item.classes, list):
            item.classes = []
        if not isinstance(item.jumbo_mtu, bool):
            item.jumbo_mtu = False
        target = item.target_platform.lower().replace(" ", "_")
        if item.configure_recommended_classes:
            item.classes = kwargs.ezdata[f'intersight.{self.category}.system_qos.templates'].properties[
                f'recommended_classes_{target}'].classes
        elif item.configure_default_classes:
            item.classes = kwargs.ezdata[f'intersight.{self.category}.system_qos.templates'].properties[
                f'default_classes_{target}'].classes
        elif len(item.classes) == 0:
            item.classes = kwargs.ezdata[f'intersight.{self.category}.system_qos.templates'].properties[
                f'default_classes_{target}'].classes
        # weight_total = 0
        for x in range(0, len(item.classes)):
            if item.classes[x].priority == 'FC':
                item.classes[x].mtu = 2240
            elif item.jumbo_mtu:
                item.classes[x].mtu = 9216
            else:
                item.classes[x].mtu = 1500
        return item

    # =========================================================================
    # Function - Assign LDAP Groups to LDAP Policies
    # =========================================================================
    def policies_ldap_ldap_groups(self, kwargs):
        names = []
        for item in kwargs.resources:
            ikeys = list(item.keys())
            if 'ldap_groups' in ikeys and len(item.ldap_groups) > 0:
                names.extend([e.get('end_point_role')
                             for e in item.ldap_groups if e.get('end_point_role')])
        if len(names) > 0:
            kwargs = kwargs | DotMap(
                method='get',
                names=list(
                    numpy.unique(
                        numpy.array(names))),
                uri='iam/EndPointRoles')
            kwargs = api(
                category='system',
                type='iam_end_point_role').calls(kwargs)
        kwargs = self.children_resources('ldap_groups', kwargs)
        return kwargs

    # =========================================================================
    # Function - Assign LDAP Servers to LDAP Policies
    # =========================================================================
    def policies_ldap_ldap_servers(self, kwargs):
        kwargs = self.children_resources('ldap_servers', kwargs)
        return kwargs

    # =========================================================================
    # Function - Port Policies - Sub Policies
    # =========================================================================
    def policies_port_children(self, kwargs):
        # =====================================================================
        # Get Existing Port Types Assigned to Port Policies
        # =====================================================================
        org = kwargs.org
        np, ns = self.name_prefix_suffix(org, kwargs)
        port_types = [k.split('.')[-1] for k, v in kwargs.ezdata.items()
                      if re.search(r'^intersight\.policies\.port\.port_[a-z_]+$', k)]
        port_types = [e for e in port_types if e != 'port_modes']
        port_types.insert(0, 'port_modes')
        port = DotMap()
        for e in port_types:
            port[e] = DotMap(names=[])
        # =====================================================================
        # Check for Parent Port Policies and Get Existing Port Type
        # Assignments for Each Parent Policy.  Skip if No Parent Policies
        # Exist or if Running in Check Mode.
        # =====================================================================
        continue_count = 0
        ikeys = list(kwargs.intersight_api[org].policies.port.keys())
        for item in kwargs.resources:
            policy_list = [
                f"{np}{e}{ns}" for e in item.names if f"{np}{e}{ns}" in ikeys]
            continue_count += len(policy_list)
            if kwargs.args.check and len(policy_list) != len(item.names):
                pcolor.Cyan("\n     * Running in Check Mode")
            if len(policy_list) != len(item.names):
                pcolor.Yellow(
                    f"\n     * Skipping Port Policy Children Retrieval for Org: {org} > Port Policies:")
                pcolor.Yellow(
                    f"       {', '.join([f'`{np}{d}{ns}`' for d in item.names])} because no parent Port Policy exists in Intersight.")
        if continue_count == 0:
            return kwargs
        # =====================================================================
        # Get Parent Port Policies
        # =====================================================================
        for e in port_types:
            for item in kwargs.resources:
                ikeys = list(item.keys())
                if e in ikeys and len(item[e]) > 0:
                    try:
                        port[e].names.extend(
                            [kwargs.intersight_api[org]['policies']['port'][f"{np}{d}{ns}"].moid for d in item.names])
                    except KeyError as ex:
                        pcolor.Red(
                            f"Warning: Missing port policy key for {e}: {ex}")
        for e in port_types:
            if len(port[e].names) > 0:
                port[e].names = list(numpy.unique(numpy.array(port[e].names)))
                kwargs = configure(
                    category=self.category,
                    type=f'{self.type}.{e}').api_get(
                    True,
                    port[e].names,
                    f'port.{e}',
                    kwargs)
        # =====================================================================
        # Generate Port Types Content
        # =====================================================================

        def pitem_generation(x, item, policy, kwargs):
            ikeys = list(item.keys())
            try:
                parent = kwargs.intersight_api[kwargs.org]['policies'][
                    'port'][f"{np}{item['names'][x]}{ns}"].moid
            except KeyError as ex:
                pcolor.Red(f"Warning: Missing parent port policy: {ex}")
                return None
            pitem = DotMap({'parent': parent} | policy.toDict())
            if 'tags' in ikeys:
                pitem.tags = item.tags
            return pitem
        # =====================================================================
        # Unified Port Handler with Dispatch
        # =====================================================================

        def process_port_attributes(pitem, policy, port_type, x):
            """Apply port-type-specific attribute processing."""
            if pitem is None:
                return
            pkeys = list(policy.keys())
            if port_type == 'channel':
                plist = [
                    'ethernet_network_group_policies',
                    'pc_ids',
                    'user_labels',
                    'vsan_ids']
                for p in plist:
                    new_label = p[:-1] if p in ['pc_ids',
                                                'user_labels', 'vsan_ids'] else p
                    if 'ethernet_network_group_policies' == p:
                        half = len(policy[p]) // 2
                        if len(policy[p]) > 1:
                            eng_value = policy[p][:half] if x == 0 else policy[p][half:]
                        else:
                            eng_value = policy[p]
                        pitem['ethernet_network_group_policies'] = eng_value
                        if isinstance(eng_value, list) and len(eng_value) > 0:
                            pitem['ethernet_network_group_policy'] = eng_value[0]
                        else:
                            pitem['ethernet_network_group_policy'] = eng_value
                    else:
                        pitem[new_label] = policy[p][x] if p in pkeys and len(
                            policy[p]) > 1 else policy[p][0] if p in pkeys else None
            elif port_type == 'role':
                plist = [
                    'ethernet_network_group_policies',
                    'user_labels',
                    'vsan_ids']
                port_list = shared_functions.vlan_list_full(pitem.port_list)
                ports_length = len(port_list)
                for num in range(ports_length):
                    pitem.port_id = port_list[num]
                    for p in plist:
                        new_label = p[:-1] if p in ['user_labels',
                                                    'vsan_ids'] else p
                        if p in pkeys:
                            double = ports_length * 2
                            half = len(policy[p]) // 2
                            if len(policy[p]) == double and x == 0:
                                value = policy[p][:half][num]
                            elif len(policy[p]) == double and x == 1:
                                value = policy[p][half:][num]
                            elif len(policy[p]) == ports_length:
                                value = policy[p][num]
                            else:
                                value = policy[p][0]

                            # Keep ethernet network group references list-shaped
                            # for templates that consume index 0.
                            if p == 'ethernet_network_group_policies':
                                eng_value = value if isinstance(
                                    value, list) else [value]
                                pitem['ethernet_network_group_policies'] = eng_value
                                pitem['ethernet_network_group_policy'] = eng_value[0] if len(
                                    eng_value) > 0 else ''
                            else:
                                pitem[new_label] = value

        def create_and_commit_api(pitem, e, kwargs):
            """Create API body and compare against existing state."""
            if pitem is None:
                return kwargs
            api_body = configure(
                category=self.category,
                type=f'port.{e}').create_api_body(
                pitem,
                np,
                ns,
                kwargs)
            kwargs = configure(
                category=self.category,
                type=f'port.{e}').children_compare_api_body(
                api_body,
                kwargs)
            return kwargs

        # Map port type patterns to handler types
        port_type_handlers = {
            'port_channel': 'channel',
            'port_mode': 'mode',
            'port_role': 'role'
        }
        # =====================================================================
        # Loop through Port Types and Generate API Bodies for Each Port
        # Policy, then POST via API if Bulk List > 0
        # =====================================================================
        for e in port_types:
            kwargs.bulk_list = []
            for item in kwargs.resources:
                ikeys = list(item.keys())
                if e in ikeys and len(item[e]) > 0:
                    for x in range(0, len(item['names'])):
                        for policy in item[e]:
                            pitem = pitem_generation(x, item, policy, kwargs)
                            # Determine handler type from port type name
                            handler_type = next(
                                (v for k, v in port_type_handlers.items() if k in e), None)
                            if handler_type == 'channel' or handler_type == 'role':
                                process_port_attributes(
                                    pitem, policy, handler_type, x)
                            kwargs = create_and_commit_api(pitem, e, kwargs)
            if len(kwargs.bulk_list) > 0:
                kwargs.uri = kwargs.ezdata[f"intersight.{self.category}.port.{e}"]['x-intersight-uri']
                kwargs = configure(
                    category=self.category,
                    type=f'port.{e}').create_bulk_request(kwargs)
        return kwargs

    # =========================================================================
    # Function - Assign vNICs to LAN Connectivity Policies
    # =========================================================================
    def policies_lan_connectivity_vnics(self, kwargs):
        kwargs = self.policies_vnics_compile('vnics', kwargs)
        return kwargs

    # =========================================================================
    # Function - Assign vNICs to LAN Connectivity Policies from Template
    # =========================================================================
    def policies_lan_connectivity_vnics_from_template(self, kwargs):
        kwargs = self.policies_vnics_compile('vnics_from_template', kwargs)
        return kwargs

    # =========================================================================
    # Function - Assign Users to Local User Policies
    # =========================================================================
    def policies_local_user_users(self, kwargs):
        names = []
        for item in kwargs.resources:
            ikeys = list(item.keys())
            if 'users' in ikeys and len(item.users) > 0:
                names.extend([e.get('role')
                             for e in item.users if e.get('role')])
        if len(names) > 0:
            kwargs = kwargs | DotMap(
                method='get',
                names=list(
                    numpy.unique(
                        numpy.array(names))),
                uri='iam/EndPointRoles')
            kwargs = api(
                category='system',
                type='iam_end_point_role').calls(kwargs)
        kwargs = self.children_resources('users', kwargs)
        kwargs = self.children_resources('users_roles', kwargs)
        return kwargs

    # =========================================================================
    # Function - SNMP Policy Port Validation
    # =========================================================================
    def policies_snmp(self, kwargs):
        reserved_ports = [
            22,
            23,
            80,
            123,
            389,
            443,
            623,
            636,
            2068,
            3268,
            3269]
        policy_name = ''
        for item in kwargs.resources:
            policy_name = f"{item.name}" if hasattr(item, 'name') else ''
            ikeys = list(item.keys())
            if 'snmp_trap_destinations' in ikeys and len(
                    item.snmp_trap_destinations) > 0:
                for trap in item.snmp_trap_destinations:
                    if trap.get('port'):
                        trap_port = int(trap['port'])
                        if trap_port in reserved_ports:
                            pcolor.Red(
                                f"!!! ERROR !!! SNMP Policy `{policy_name}`: Trap destination port {trap_port} is a reserved port. "
                                f"Reserved ports not allowed: {', '.join(map(str, reserved_ports))}")
                            raise ValueError(
                                f"SNMP policy `{policy_name}` uses reserved trap destination port {trap_port}. "
                                f"Reserved ports: {', '.join(map(str, reserved_ports))}")
        return kwargs

    # =========================================================================
    # Function - Assign vHBAs to SAN Connectivity Policies
    # =========================================================================
    def policies_san_connectivity_vhbas(self, kwargs):
        kwargs = self.policies_vnics_compile('vhbas', kwargs)
        return kwargs

    # =========================================================================
    # Function - Assign vHBAs to SAN Connectivity Policies from Template
    # =========================================================================
    def policies_san_connectivity_vhbas_from_template(self, kwargs):
        kwargs = self.policies_vnics_compile('vhbas_from_template', kwargs)
        return kwargs

    # =========================================================================
    # Function - Storage Policy Updates
    # =========================================================================
    def policies_storage(self, item, kwargs):
        ikeys = list(item.keys())
        ptitle = notifications.mod_pol_description(
            (self.type.replace('_', ' ').title()))
        if 'storage_template' in ikeys:
            templates = kwargs.ezdata[f'intersight.{self.category}.{self.type}.templates'].properties
            template_name = item.storage_template
            if template_name not in templates:
                pcolor.Red(
                    f'!!! ERROR !!! {ptitle} Template "{template_name}" was not found in "intersight.{self.category}.{self.type}.templates".')
                pcolor.Red(
                    f'Available templates are: {", ".join(sorted(list(templates.keys())))}')
                raise ValueError(
                    f'{ptitle} template "{template_name}" was not found in "intersight.{self.category}.{self.type}.templates"')
            merged = deepcopy(templates[template_name].toDict())
            merged = self.deep_merge_dicts(merged, item.toDict())
            item = DotMap(merged)
        return item

    # =========================================================================
    # Function - Assign Drive Groups to Storage Policies
    # =========================================================================
    def policies_storage_drive_groups(self, kwargs):
        kwargs = self.children_resources('drive_groups', kwargs)
        return kwargs

    # =========================================================================
    # Function - Assign VLANs to VLAN Policies
    # =========================================================================
    def policies_vlan_vlans(self, kwargs):
        child_type = 'vlans'
        continue_count, kwargs = self.children_check_parent(child_type, kwargs)
        if continue_count == 0:
            return kwargs
        # =====================================================================
        # Create API Body for Sub Items and Compare to Existing API Results.
        # If Differences or No Existing Resource, Append to Bulk List for
        # POST/PATCH.  If No Differences, Skip.
        # =====================================================================
        org = kwargs.org
        np, ns = self.name_prefix_suffix(org, kwargs)
        kwargs.bulk_list = []
        for e in kwargs.resources:
            ekeys = list(e.keys())
            if child_type in ekeys:
                for item in e[child_type]:
                    ikeys = list(item.keys())
                    item.parent = kwargs.intersight_api[org][self.category][self.type][np + e.name + ns].moid
                    if 'name_prefix' not in ikeys:
                        name_prefix = True
                    else:
                        name_prefix = item.name_prefix
                    vlans = shared_functions.vlan_list_full(item.vlan_list)
                    original_name = item.name
                    reserved_list = shared_functions.vlan_list_full(
                        '4043-4047, 4094, 4095')
                    for x in vlans:
                        if isinstance(x, str):
                            x = int(x)
                        if x in reserved_list:
                            pcolor.Yellow(
                                f'!!! WARNING !!! VLAN ID {x} is a reserved VLAN and cannot be used.'
                                f'  Skipping assignment of VLAN ID {x} under VLAN Policy `{np + e.name + ns}` in Org `{kwargs.org}`.')
                            continue
                        if len(vlans) > 1 and name_prefix:
                            item.name = deepcopy(f"{original_name}{x}")
                            # item.name = deepcopy(f"{original_name}{'0'*(4 - len(str(x)))}{x}")
                        else:
                            item.name = deepcopy(f"{original_name}")
                        item.vlan_id = x
                        item.target_platform = e.get(
                            'target_platform', 'UCS Domain')
                        api_body = configure(
                            category=self.category,
                            type=f'{self.type}.{child_type}').create_api_body(
                            item,
                            np,
                            ns,
                            kwargs)
                        kwargs = configure(
                            category=self.category,
                            type=f'{self.type}.{child_type}').children_compare_api_body(
                            api_body,
                            kwargs)
        if len(kwargs.bulk_list) > 0:
            kwargs.uri = kwargs.ezdata[f"intersight.{self.category}.{self.type}.{child_type}.domain"]['x-intersight-uri']
            kwargs = configure(
                category=self.category,
                type=f'{self.type}.{child_type}').create_bulk_request(kwargs)
        return kwargs

    # =========================================================================
    # Function - Assign VNICs to LAN Connectivity Policies
    # =========================================================================
    def policies_vnics_compile(self, child_type, kwargs):
        continue_count, kwargs = self.children_check_parent(child_type, kwargs)
        if continue_count == 0:
            return kwargs
        np, ns = self.name_prefix_suffix(kwargs.org, kwargs)
        # =====================================================================
        # Create API Body for Sub Items and Compare to Existing API Results.
        # If Differences or No Existing Resource, Append to Bulk List for
        # POST/PATCH.  If No Differences, Skip.
        # =====================================================================
        # Normalize legacy scalar/list forms so compile logic can treat inputs
        # consistently.

        def normalize_child_item(item, x):
            placement_key_map = {
                'pci_links': 'pci_link',
                'pci_order': 'pci_order',
                'slot_ids': 'slot_id',
                'switch_ids': 'switch_id',
                'uplink_ports': 'uplink_port'
            }
            rename_key_map = {
                'ethernet_adapter_policies': 'ethernet_adapter_policy',
                'ethernet_network_policies': 'ethernet_network_policy',
                'ethernet_network_control_policies': 'ethernet_network_control_policy',
                'ethernet_network_group_policies': 'ethernet_network_group_policies',
                'ethernet_qos_policies': 'ethernet_qos_policy',
                'fibre_channel_network_policies': 'fibre_channel_network_policy',
                'fc_zone_policies': 'fc_zone_policies',
                'flow_monitor_policies': 'flow_monitor_policies',
                'iscsi_boot_policies': 'iscsi_boot_policy',
                'mac_address_pools': 'mac_address_pool',
                'wwpn_pools': 'wwpn_pool',
                'mac_addresses_static': 'mac_address_static'}
            list_policy_keys = {
                'ethernet_network_group_policies',
                'fc_zone_policies',
                'flow_monitor_policies',
            }
            if 'template' not in child_type:
                if item.get('placement') and isinstance(item.placement, dict):
                    for plural_key, singular_key in placement_key_map.items():
                        if plural_key in item.placement and isinstance(
                                item.placement[plural_key], list) and len(
                                item.placement[plural_key]) > 0:
                            if len(
                                    item.placement[plural_key]) == len(
                                    item.names):
                                item.placement[singular_key] = item.placement[plural_key][x]
                            else:
                                item.placement[singular_key] = item.placement[plural_key][0]
                    if item.placement.get('switch_id', None) in [None, '']:
                        item.placement['switch_id'] = 'A' if x == 0 else 'B'
                for original, new in rename_key_map.items():
                    if original in item and isinstance(
                            item[original], list) and len(
                            item[original]) > 0:
                        src_len = len(item[original])
                        names_len = len(item.names)
                        if src_len > names_len:
                            if original in list_policy_keys:
                                if names_len > 0 and src_len % names_len == 0:
                                    chunk = int(src_len / names_len)
                                    start = x * chunk
                                    item[new] = item[original][start:start + chunk]
                                elif names_len == 2:
                                    half = int(src_len / 2)
                                    if x == 1:
                                        item[new] = item[original][half:]
                                    else:
                                        item[new] = item[original][:half]
                                else:
                                    item[new] = item[original]
                            else:
                                if x < src_len:
                                    item[new] = item[original][x]
                                else:
                                    item[new] = item[original][0]
                        elif src_len == names_len:
                            if original in list_policy_keys:
                                item[new] = [item[original][x]]
                            else:
                                item[new] = item[original][x]
                        else:
                            if original in list_policy_keys:
                                item[new] = item[original]
                            else:
                                item[new] = item[original][0]
            return item
        # =================================================================
        # Function - vNIC Loop - Build API Body
        # =================================================================

        def vnic_loop(item, x, kwargs):
            if 'template' in child_type:
                cdict = child_type.replace('s_template', '_template')
                torg, tname = self.determine_resource_organization(
                    add_prefix_suffix=True, resource=item[cdict], kwargs=kwargs)
                item.allow_override = kwargs.intersight_api[torg].policies[cdict][tname].result['AllowOverride']
            else:
                item.name = item.names[x]
            item = normalize_child_item(item, x)
            np = ''
            ns = ''
            api_body = configure(
                category=self.category,
                type=f'{self.type}.{child_type}').create_api_body(
                item,
                np,
                ns,
                kwargs)
            kwargs = configure(
                category=self.category,
                type=f'{self.type}.{child_type}').children_compare_api_body(
                api_body,
                kwargs)
            return kwargs
        # =====================================================================
        # Create API Body for vHBAs/vNICs
        # =====================================================================
        kwargs.bulk_list = []
        for item in kwargs.resources:
            ikeys = list(item.keys())
            if child_type in ikeys:
                # =================================================================
                # Loop Through vHBA/vNICs
                # =================================================================
                for i in item[child_type]:
                    i.parent = kwargs.intersight_api[kwargs.org][self.category][self.type][np +
                                                                                           item.name + ns].moid
                    i.target_platform = item.get(
                        'target_platform', 'FIAttached')
                    if 'template' in child_type:
                        kwargs = vnic_loop(i, 99, kwargs)
                    else:
                        original_items = deepcopy(i)
                        for x in range(len(i.names)):
                            kwargs = vnic_loop(
                                deepcopy(original_items), x, kwargs)
        if len(kwargs.bulk_list) > 0:
            kwargs.uri = kwargs.ezdata[f"intersight.{self.category}.{self.type}.{child_type}"]['x-intersight-uri']
            if isinstance(kwargs.uri, DotMap):
                kwargs.uri = kwargs.ezdata[f"intersight.{self.category}.{self.type}.{child_type}.domain"]['x-intersight-uri']
            kwargs = configure(
                category=self.category,
                type=f'{self.type}.{child_type}').create_bulk_request(kwargs)
        return kwargs

    # =========================================================================
    # Function - Assign VSANs to VSAN Policies
    # =========================================================================
    def policies_vsan_vsans(self, kwargs):
        kwargs = self.children_resources('vsans', kwargs)
        return kwargs

    # =========================================================================
    # Function - Merge Template with Chassis/Domain/Server Profile
    # =========================================================================
    def profiles_bulk_merge_template(self, kwargs):
        original_org = kwargs.org
        kwargs.bulk_templates = DotMap()
        skeys = kwargs.intersight_api[original_org].profiles[self.type.replace(
            '.switch', '')]
        np, ns = self.name_prefix_suffix(original_org, kwargs)
        for e in kwargs.resources:
            name = f'{np}{e.name}{ns}'
            template = next(
                (k for k in e.keys() if template_regex.match(k)), None)
            template_value = e.get(template)
            if not template or not template_value:
                pcolor.Yellow(
                    f'  * Skipping Org: {kwargs.org}; Profile `{name}` has no valid template reference key.')
                continue
            org, tname = self.determine_resource_organization(
                add_prefix_suffix=False, resource=template_value, kwargs=kwargs)
            kwargs.bulk_templates.setdefault(org, DotMap())
            if 'switch' in self.type:
                for switch_id in ['A', 'B']:
                    src_template_merged = all(
                        [
                            name in skeys and skeys[name],
                            (skeys[name].get(
                                'result',
                                {}).get('SrcTemplate') or {}).get('Moid') if skeys.get(name) else False,
                            skeys[name].get(
                                'switch',
                                {}).get(f'{name}-{switch_id}') if skeys.get(name) else False,
                            (skeys[name].get(
                                'switch',
                                {}).get(
                                f'{name}-{switch_id}',
                                {}).get('SrcTemplate') or {}).get('Moid') if skeys.get(name) else False])
                    if src_template_merged:
                        continue
                    sw_template = f"{tname}-{switch_id}"
                    if not kwargs.bulk_templates[org].get(sw_template):
                        tdata = kwargs.intersight_api[org].templates.domain['switch'][sw_template].result
                        if tdata is None:
                            pcolor.Red(
                                f'!!! ERROR !!! Template "{sw_template}" not found in Intersight Org "{org}". Cannot perform bulk merge for profile "{name}".')
                            raise ValueError(
                                f'Template "{sw_template}" not found in Intersight Org "{org}" during bulk merge for profile "{name}"')
                        kwargs.bulk_templates[org][sw_template] = {
                            'MergeAction': 'Merge', 'ObjectType': 'bulk.MoMerger', 'Targets': [],
                            'Sources': [{'Moid': tdata.Moid, 'ObjectType': tdata.ObjectType}]}
                    pdata = kwargs.intersight_api[original_org].profiles.domain[
                        f"{name}-{switch_id}"].result
                    pdict = {
                        'Moid': pdata.Moid,
                        'ObjectType': pdata.ObjectType}
                    kwargs.bulk_templates[org][sw_template]['Targets'].append(
                        pdict)
            elif not (name in skeys and skeys[name] and (skeys[name].get('result', {}).get('SrcTemplate') or {}).get('Moid')):
                if not kwargs.bulk_templates[org].get(tname):
                    tdata = kwargs.intersight_api[org].templates[self.type][tname].result
                    if tdata is None:
                        pcolor.Red(
                            f'!!! ERROR !!! Template "{tname}" not found in Intersight Org "{org}". Cannot perform bulk merge for profile "{name}".')
                        raise ValueError(
                            f'Template "{tname}" not found in Intersight Org "{org}" during bulk merge for profile "{name}"')
                kwargs.bulk_templates[org][tname] = {
                    'MergeAction': 'Merge', 'ObjectType': 'bulk.MoMerger', 'Targets': [],
                    'Sources': [{'Moid': tdata.Moid, 'ObjectType': tdata.ObjectType}]}
                pdata = kwargs.intersight_api[original_org].profiles[
                    self.type][f'{name}'].result
                pdict = {'Moid': pdata.Moid, 'ObjectType': pdata.ObjectType}
                kwargs.bulk_templates[org][tname]['Targets'].append(pdict)
        # =====================================================================
        # POST bulk/MoMergers if Map > 0 and return kwargs
        # =====================================================================
        if kwargs.bulk_templates:
            batch_size = 100

            def dedupe_moid_objects(items):
                unique = []
                seen = set()
                for item in items:
                    key = (item.get('Moid'), item.get('ObjectType'))
                    if key in seen:
                        continue
                    seen.add(key)
                    unique.append(item)
                return unique

            def post_to_api(api_body, kwargs):
                kwargs = kwargs | DotMap(
                    api_body=api_body, method='post', uri='bulk/MoMergers')
                kwargs = api(
                    category=self.category,
                    type='bulk_merger').calls(kwargs)
                return kwargs
            orgs = kwargs.bulk_templates.keys()
            for org in orgs:
                kwargs.org = org
                for k, v in kwargs.bulk_templates[org].items():
                    kwargs.bulk_templates[org][k]['Targets'] = dedupe_moid_objects(
                        kwargs.bulk_templates[org][k]['Targets'])
                    kwargs.bulk_templates[org][k]['Sources'] = dedupe_moid_objects(
                        kwargs.bulk_templates[org][k]['Sources'])
                    if len(v['Targets']) > batch_size:
                        request_list = deepcopy(v['Targets'])
                        for i in range(0, len(request_list), batch_size):
                            targets = request_list[i:i + batch_size]
                            v['Targets'] = targets
                            kwargs = post_to_api(v, kwargs)
                    elif v['Targets']:
                        kwargs = post_to_api(v, kwargs)
        kwargs.org = original_org
        return kwargs

    # =========================================================================
    # Function - Chassis Profiles Updates
    # =========================================================================
    def profiles_chassis(self, kwargs):
        kwargs = self.profiles_chassis_server(kwargs)
        return kwargs

    # =========================================================================
    # Function - Build Chassis/Server Profiles
    # =========================================================================
    def profiles_chassis_server(self, kwargs):
        ezdata = kwargs.ezdata[f'intersight.profiles.{self.type}']
        np, ns = self.name_prefix_suffix(kwargs.org, kwargs)
        ptitle = notifications.mod_pol_description(
            (self.type.replace('_', ' ').title()))
        kwargs.merge_templates = DotMap()
        # =====================================================================
        # Lookup Serial Number Assignments for Chassis/Server Profiles
        # =====================================================================
        serial_numbers = []
        for item in kwargs.resources:
            ikeys = list(item.keys())
            if 'serial_number' in ikeys and re.search(
                    serial_regex, item.serial_number):
                serial_numbers.append(item.serial_number)
        if serial_numbers:
            kwargs = kwargs | DotMap(
                method='get',
                names=serial_numbers,
                uri=ezdata['x-intersight-uri-serial'])
            kwargs = api(category='system', type='serial_number').calls(kwargs)
        # =====================================================================
        # Assign Server Profile Identity Reservations - If Defined
        # =====================================================================
        reservations = False
        if self.type == 'server':
            for item in kwargs.resources:
                ikeys = list(item.keys())
                if 'reservations' in ikeys:
                    reservations = True

        def assign_uuid_type(api_body, item, kwargs):
            if item.get('ucs_server_profile_template') and item.get('attach_template', False) is True:
                template_name = item.ucs_server_profile_template
                org, tname = self.determine_resource_organization(
                    add_prefix_suffix=False, resource=template_name, kwargs=kwargs)
                template_data = kwargs.intersight_api[org].templates.server[tname].result
                if template_data and template_data.get('UuidAddressType'):
                    api_body['UuidAddressType'] = template_data['UuidAddressType']
                    if template_data['UuidAddressType'] == 'POOL':
                        api_body['UuidPool'] = template_data['UuidPool'][0].get('Moid')
                    elif template_data['UuidAddressType'] == 'STATIC' and len(item.get('static_uuid_address', '')) > 0:
                        api_body['StaticUuidAddress'] = item.get('static_uuid_address', '')
            elif item.get('static_uuid_address') and len(item.static_uuid_address) > 0:
                api_body['UuidAddressType'] = 'STATIC'
                api_body['StaticUuidAddress'] = item.static_uuid_address
            elif item.get('uuid_pool'):
                pool_name = item.uuid_pool
                org, pname = self.determine_resource_organization(
                    add_prefix_suffix=False, resource=pool_name, kwargs=kwargs)
                pool_data = kwargs.intersight_api[org].policies.server.uuid_pool[pname].result
                if pool_data:
                    api_body['UuidAddressType'] = 'POOL'
                    api_body['UuidPool'] = pool_data.get('Moid')
            else:
                api_body['UuidAddressType'] = 'NONE'
            return api_body
        if reservations:
            kwargs = self.profiles_server_identity_reservations(kwargs)
            kwargs.bulk_list = []
            for item in kwargs.resources:
                ikeys = list(item.keys())
                name = f'{np}{item.name}{ns}'
                if kwargs.intersight_api[kwargs.org].profiles.server.get(name):
                    continue
                if 'reservations' in ikeys:
                    api_body = {
                        'Name': name,
                        'ObjectType': ezdata['x-intersight-object-type'],
                        'ServerFamily': item.get('server_family', 'All'),
                        'TargetPlatform': item.get('target_platform', 'FIAttached')}
                    api_body = assign_uuid_type(api_body, item, kwargs)
                    api_body = self.profiles_org_map(api_body, kwargs.org_moids[kwargs.org].moid)
                    api_body = self.profiles_server_reservations(item, api_body, kwargs)
                    if api_body.get('ReservationReferences'):
                        kwargs.bulk_list.append(api_body)
                    else:
                        kwargs.bulk_list.append(api_body)
        else:
            kwargs.bulk_list = []
            for item in kwargs.resources:
                name = f'{np}{item.name}{ns}'
                if kwargs.intersight_api[kwargs.org].profiles[self.type].get(name):
                    continue
                if self.type == 'server':
                    api_body = {
                        'Name': name,
                        'ObjectType': ezdata['x-intersight-object-type'],
                        'ServerFamily': item.get('server_family', 'All'),
                        'TargetPlatform': item.get('target_platform', 'FIAttached')}
                    api_body = assign_uuid_type(api_body, item, kwargs)
                else:
                    api_body = {'Name': name, 'ObjectType': ezdata['x-intersight-object-type']}
                api_body = self.profiles_org_map(api_body, kwargs.org_moids[kwargs.org].moid)
                kwargs.bulk_list.append(api_body)
        # =================================================================
        # POST bulk/Requests if Bulk List > 0 - Initial Profile
        # =================================================================
        if len(kwargs.bulk_list) > 0:
            kwargs.uri = ezdata['x-intersight-uri']
            kwargs = self.create_bulk_request(kwargs)
        # =====================================================================
        # Attach Templates either through Bulk Merger or Merging Dicts
        # =====================================================================
        kwargs.bulk_list = []
        template_attach = False
        template_merge = False
        template_type = None
        for e in kwargs.resources:
            if any(template_regex.match(k) for k in e.keys()):
                template_type = next(
                    (k for k in e.keys() if template_regex.match(k)), None)
                if e.get('attach_template', True):
                    template_attach = True
                elif e.get('attach_template', True) is False:
                    template_merge = True
        if template_attach:
            kwargs = self.profiles_bulk_merge_template(kwargs)
        elif template_merge:
            kwargs = self.profiles_template_lookup(template_type, kwargs)
        # =====================================================================
        # Update Intersight with Server Profile Configuration
        # =====================================================================
        kwargs.bulk_list = []
        for item in kwargs.resources:
            ikeys = list(item.keys())
            if item.get('attach_template') is False and any(
                    template_regex.match(k) for k in ikeys):
                template_type = next(
                    (k for k in ikeys if template_regex.match(k)), None)
                item = self.profiles_template_merge(
                    item, item[template_type], ptitle, kwargs)
            api_body = self.create_api_body(item, np, ns, kwargs)
            kwargs = self.compare_resources_to_api(api_body, ptitle, kwargs)
        # POST Bulk Request if List > 0
        if len(kwargs.bulk_list) > 0:
            kwargs.uri = ezdata['x-intersight-uri']
            kwargs = self.create_bulk_request(kwargs)
        # =====================================================================
        # PATCH Profiles if has attach_template True and has a Description
        # =====================================================================
        kwargs.bulk_list = []
        for item in kwargs.resources:
            ikeys = list(item.keys())
            if item.get('attach_template') is False and any(
                    template_regex.match(k) for k in ikeys):
                name = f'{np}{item.name}{ns}'
                api_body = dict(Description='', Name=name, ObjectType=ezdata['x-intersight-object-type'],
                                pmoid=kwargs.intersight_api[kwargs.org].profiles[self.type][name])
                if 'description' in ikeys:
                    api_body['Description'] = item.description
                else:
                    api_body['Description'] = f'{name} {self.type.capitalize()} Profile.'
                kwargs.bulk_list.append(api_body)
        if len(kwargs.bulk_list) > 0:
            pcolor.Cyan('')
            pcolor.Cyan(
                f'{" " * 3}Updating {self.type.capitalize()} Profile Descriptions.')
            kwargs.uri = ezdata['x-intersight-uri']
            kwargs = self.create_bulk_request(kwargs)
        # =====================================================================
        # If Action is Deploy; Deploy the Profile
        # =====================================================================
        profiles = []
        for e in kwargs.resources:
            if 'action' in e and e.action == 'Deploy':
                profiles.append(e)
        if profiles:
            kwargs = self.profiles_chassis_server_deploy(profiles, kwargs)
        return kwargs

    # =========================================================================
    # Function - Deploy Profile if Action is Deploy
    # =========================================================================
    def profiles_chassis_server_deploy(self, profiles, kwargs):
        np, ns = self.name_prefix_suffix(kwargs.org, kwargs)
        profile_api = api(category=self.category, type=self.type)
        cregex = re.compile(
            'Analyzing|Assigned|Failed|Inconsistent|Validating')
        pending_changes = False
        kwargs.profile_update = DotMap()
        kwargs.uri = kwargs.ezdata[f"intersight.profiles.{self.type}"]['x-intersight-uri']
        for e in profiles:
            if 'action' in e and 'serial_number' in e and re.search(
                    serial_regex, e.serial_number):
                kwargs.profile_update[f'{np}{e.name}{ns}'] = e
                kwargs.profile_update[f'{np}{e.name}{ns}'].pending_changes = 'Empty'
        if kwargs.profile_update:
            names = list(kwargs.profile_update.keys())
            kwargs = self.api_get(False, names, self.type, kwargs)
            profile_map = kwargs.intersight_api[kwargs.org].profiles[self.type]
            for e in names:
                profile_data = profile_map.get(e)
                if not profile_data:
                    pcolor.Yellow(
                        f'  * Skipping Org: {kwargs.org}; Profile `{e}` not found in API lookup.')
                    continue
                pdata = profile_data.result
                changes = pdata.get('ConfigChanges', {}).get('Changes', [])
                cstate = pdata.get(
                    'ConfigContext', {}).get('ConfigState') or ''
                csummary = pdata.get('ConfigContext', {}).get(
                    'ConfigStateSummary') or ''
                if changes or re.search(
                        cregex, cstate) or re.search(
                        cregex, csummary):
                    pending_changes = True
                    kwargs.profile_update[e].pending_changes = 'Deploy'
                elif pdata.get('ConfigChanges', {}).get('PolicyDisruptions', []):
                    pending_changes = True
                    kwargs.profile_update[e].pending_changes = 'Activate'
            if pending_changes:
                pcolor.LightPurple(f'\n{"-" * 108}\n')
                deploy_pending = any(
                    kwargs.profile_update[e].pending_changes == 'Deploy' for e in names)
                activate_pending = any(
                    kwargs.profile_update[e].pending_changes == 'Activate' for e in names)
                if deploy_pending:
                    if 'server' == self.type:
                        pcolor.LightPurple(
                            f'{" " * 4}* Pending Changes.  Sleeping for 120 Seconds')
                        time.sleep(120)
                    else:
                        pcolor.LightPurple(
                            '    * Pending Changes.  Sleeping for 60 Seconds')
                        time.sleep(60)
                for e in names:
                    if kwargs.profile_update[e].pending_changes == 'Deploy':
                        pcolor.Green(
                            f'{" " * 4}- Beginning Profile Deployment for `{e}`.')
                        kwargs = kwargs | DotMap(
                            api_body={
                                'Action': 'Deploy',
                                'Name': e},
                            method='patch',
                            pmoid=profile_map[e].moid)
                        kwargs = profile_api.calls(kwargs)
                    elif kwargs.profile_update[e].pending_changes == 'Activate':
                        pcolor.LightPurple(
                            f'{" " * 4}- Skipping Org: {kwargs.org}; Profile Deployment for `{e}`.  Pending Activation.')
                    else:
                        pcolor.LightPurple(
                            f'{" " * 4}- Skipping Org: {kwargs.org}; Profile Deployment for `{e}`.  No Pending Changes.')
                if deploy_pending:
                    if 'server' == self.type:
                        pcolor.LightPurple(
                            f'{" " * 4}* Deploying Changes.  Sleeping for 600 Seconds')
                        time.sleep(600)
                    else:
                        pcolor.LightPurple(
                            f'{" " * 4}* Deploying Changes.  Sleeping for 60 Seconds')
                        time.sleep(60)
                for e in names:
                    if kwargs.profile_update[e].pending_changes == 'Deploy':
                        deploy_complete = False
                        retry_count = 0
                        max_retries = 60
                        while not deploy_complete:
                            if retry_count >= max_retries:
                                pcolor.Yellow(
                                    f'{" " * 4}- Deploy timeout waiting for `{e}` after {max_retries} checks.')
                                break
                            kwargs = kwargs | DotMap(
                                method='get_by_moid', pmoid=profile_map[e].moid)
                            kwargs = profile_api.calls(kwargs)
                            control_action = kwargs.results.get(
                                'ConfigContext', {}).get('ControlAction')
                            if control_action == 'No-op':
                                deploy_complete = True
                                if 'chassis' in self.type:
                                    pcolor.Green(
                                        f'{" " * 4}- Completed Profile Deployment for `{e}`.')
                            else:
                                if 'server' in self.type:
                                    pcolor.Cyan(
                                        f'{" " * 6}* Deploy Still Occuring on `{e}`.  Waiting 120 seconds.')
                                    time.sleep(120)
                                else:
                                    pcolor.Cyan(
                                        f'{" " * 6}* Deploy Still Occuring on `{e}`.  Waiting 60 seconds.')
                                    time.sleep(60)
                            retry_count += 1
                if 'server' == self.type and activate_pending:
                    kwargs = self.profiles_server_activate(kwargs)
                pcolor.LightPurple(f'\n{"-" * 108}\n')
        return kwargs

    # =========================================================================
    # Function - Domain Profiles Updates
    # =========================================================================
    def profiles_domain(self, kwargs):
        item = self.profiles_templates_domain_unified_edge(kwargs)
        return item

    # =========================================================================
    # Function - Deploy Domain Profile if Action is Deploy
    # =========================================================================
    def profiles_domain_deploy(self, profiles, kwargs):
        pending_changes = False
        kwargs.names = []
        np, ns = self.name_prefix_suffix(kwargs.org, kwargs)
        for e in profiles:
            name = f'{np}{e.name}{ns}'
            kwargs.cluster_update[name].names = []
            kwargs.cluster_update[name].pending_changes = False
            if e.get('action') and e.get('serial_numbers'):
                serial_check = True
                for d in e.serial_numbers:
                    if not re.search(serial_regex, d):
                        serial_check = False
                if e.action == 'Deploy' and serial_check:
                    kwargs.names.append(
                        kwargs.intersight_api[kwargs.org].profiles[self.type][name].moid)
        clusters = DotMap()
        for k, v in kwargs.intersight_api[kwargs.org].profiles[self.type].items(
        ):
            clusters[v] = k
        if len(kwargs.names) > 0:
            kwargs = kwargs | DotMap(method='get',
                                     parent='SwitchClusterProfile',
                                     uri=kwargs.ezdata[f"intersight.profiles.{self.type}"]['x-intersight-uri-switch'])
            kwargs = api('parent_moids').calls(kwargs)
            for e in kwargs.results:
                if len(
                        e.ConfigChanges.Changes) > 0 or re.search(
                        "Assigned|Failed|Pending-changes",
                        e.ConfigContext.ConfigState):
                    pending_changes = True
                    kwargs.cluster_update[clusters[e.Parent.Moid]
                                          ].pending_changes = True
                    kwargs.cluster_update[clusters[e.Parent.Moid]].names.append(
                        e.Name)
        if pending_changes:
            pcolor.LightPurple(f'\n{"-" * 108}\n')
            pcolor.Cyan(f'{" " * 6}* Sleeping for 120 Seconds')
            time.sleep(120)
            pcolor.Green(
                f'{" " * 4}- Beginning Profile Deployment for Switch Profiles')
        kwargs.bulk_list = []
        for k in list(kwargs.cluster_update.keys()):
            if kwargs.cluster_update[k].pending_changes:
                for e in kwargs.cluster_update[k].names:
                    kwargs.bulk_list.append(
                        {'Action': 'Deploy', 'Name': e, 'pmoid': kwargs.intersight_api[kwargs.org].profiles['switch'][e].moid})
        if len(kwargs.bulk_list) > 0:
            kwargs = configure('profiles.switch').create_bulk_request(kwargs)
        if pending_changes:
            pcolor.LightPurple(f'\n{"-" * 108}\n')
            time.sleep(60)
        for k in list(kwargs.cluster_update.keys()):
            if kwargs.cluster_update[k].pending_changes:
                kwargs = kwargs | DotMap(
                    method='get_by_moid', uri=kwargs.ezdata[f"intersight.profiles.{self.type}"]['x-intersight-uri-switch'])
                for e in kwargs.cluster_update[k].names:
                    kwargs.pmoid = kwargs.intersight_api[kwargs.org].profiles['switch'][e].moid
                    deploy_complete = False
                    attempts = 0
                    max_attempts = 30
                    while not deploy_complete:
                        attempts += 1
                        kwargs = api('switch_profiles').calls(kwargs)
                        if kwargs.results.ConfigContext.ControlAction == 'No-op':
                            pcolor.Green(
                                f'{" " * 4}- Completed Switch Profile Deployment for {e}')
                            deploy_complete = True
                        elif attempts >= max_attempts:
                            raise TimeoutError(
                                f'Switch profile deployment timed out for "{e}" after {attempts} checks')
                        else:
                            pcolor.Cyan(
                                f'{" " * 6}* Deploy Still Occuring on {e}.  Waiting 120 seconds.')
                            time.sleep(120)
        if pending_changes:
            pcolor.LightPurple(f'\n{"-" * 108}\n')
        return kwargs

    # =========================================================================
    # Function - Add Organization Key Map to Dictionaries
    # =========================================================================
    def profiles_org_map(self, api_body, org_moid):
        api_body.update({'Organization': {'Moid': org_moid,
                        'ObjectType': 'organization.Organization'}})
        return api_body

    # =========================================================================
    # Function - Server Profiles Updates
    # =========================================================================
    def profiles_server(self, kwargs):
        kwargs = self.profiles_chassis_server(kwargs)
        return kwargs

    # =========================================================================
    # Function - Deploy Profile if Action is Deploy
    # =========================================================================
    def profiles_server_activate(self, kwargs):
        pcolor.LightPurple(f'\n{"-" * 108}\n')
        profile_api = api(category=self.category, type=self.type)
        profile_keys = list(kwargs.profile_update.keys())
        active_profiles = [
            e for e in profile_keys if kwargs.profile_update[e].pending_changes != 'Empty']
        if active_profiles:
            kwargs = self.api_get(False, active_profiles, self.type, kwargs)
            profile_results = kwargs.results
            profile_results_by_name = {d['Name']: d for d in profile_results}
        else:
            profile_results_by_name = {}
        pending_activations = False
        for e in active_profiles:
            profile_result = profile_results_by_name.get(e)
            if not profile_result:
                pcolor.LightPurple(
                    f'{" " * 4}- Skipping Org: {kwargs.org}; Profile Activation for `{e}`.  Profile not found.')
                kwargs.profile_update[e].pending_changes = 'Empty'
                continue
            if profile_result.get(
                    'ConfigChanges', {}).get(
                    'PolicyDisruptions', []):
                pcolor.Green(
                    f'{" " * 4}- Beginning Profile Activation for `{e}`.')
                api_body = {'ScheduledActions': [
                    {'Action': 'Activate', 'ProceedOnReboot': True}]}
                kwargs = kwargs | DotMap(api_body=api_body, method='patch',
                                         pmoid=kwargs.intersight_api[kwargs.org].profiles[self.type][e].moid)
                kwargs = profile_api.calls(kwargs)
                pending_activations = True
            else:
                pcolor.LightPurple(
                    f'{" " * 4}- Skipping Org: {kwargs.org}; Profile Activation for `{e}`.  No Pending Changes.')
                kwargs.profile_update[e].pending_changes = 'Empty'
        if pending_activations:
            pcolor.LightPurple(f'\n{"-" * 108}\n')
            pcolor.LightPurple(
                '    * Pending Activations.  Sleeping for 300 Seconds')
            time.sleep(300)
        activate_moids = [kwargs.intersight_api[kwargs.org].profiles[self.type][
            e].moid for e in profile_keys if kwargs.profile_update[e].pending_changes != 'Empty']
        activate_results = []
        if activate_moids:
            dt = datetime.today().strftime('%Y-%m-%d')
            names = "', '".join(activate_moids)
            str1 = f"CreateTime gt {dt}T00:00:00.000Z and CreateTime lt {dt}T23:59:59.999Z and AssociatedObject.Moid in ('{names}')"
            str2 = " and WorkflowCtx.WorkflowType eq 'Activate'"
            kwargs = kwargs | DotMap(
                api_filter=str1 + str2,
                method='get',
                uri='workflow/WorkflowInfos')
            kwargs = api('workflows').calls(kwargs)
            activate_results = sorted(
                kwargs.results,
                key=itemgetter('CreateTime'),
                reverse=True)
        activate_results_by_moid = {}
        for result in activate_results:
            assoc_moid = result.get('AssociatedObject', {}).get('Moid')
            if assoc_moid and not activate_results_by_moid.get(assoc_moid):
                activate_results_by_moid[assoc_moid] = result

        def activation_message(e, progress, status):
            pcolor.Cyan(
                f'{" " * 6}* Still In Progress for `{e}`.  Status: `{status}` Progress Percentage: `{progress}`, Sleeping for 120 seconds.')

        def failed_message(e):
            pcolor.Yellow(f'\n{"-" * 75}\n')
            pcolor.Red(
                f'  - Failed to Activate Profile `{e}`.  Please validate in Intersight the reason for the failure.')
            pcolor.Yellow(f'\n{"-" * 75}\n')

        def success_message(e):
            pcolor.Green(f'{" " * 4}- Completed Profile Activation for `{e}`.')

        for e in profile_keys:
            if kwargs.profile_update[e].pending_changes != 'Empty':
                prmoid = kwargs.intersight_api[kwargs.org].profiles[self.type][e].moid
                active_result = activate_results_by_moid.get(prmoid)
                if not active_result:
                    failed_message(e)
                    continue
                deploy_complete = False
                retry_count = 0
                while not deploy_complete:
                    if retry_count >= 60:
                        failed_message(e)
                        deploy_complete = True
                        continue
                    if retry_count > 0:
                        kwargs = kwargs | DotMap(
                            method='get_by_moid', pmoid=active_result.Moid)
                        kwargs = api(
                            category='profiles',
                            type='workflows').calls(kwargs)
                        active_result = kwargs.results
                    status = active_result.get('WorkflowStatus')
                    if status == 'Completed':
                        success_message(e)
                        deploy_complete = True
                    elif re.search('Failed|Terminated|Canceled', status or ''):
                        failed_message(e)
                        deploy_complete = True
                    else:
                        progress = active_result.get('Progress')
                        status = active_result.get('WorkflowStatus')
                        activation_message(e, progress, status)
                        time.sleep(120)
                    retry_count += 1
            else:
                pcolor.LightPurple(
                    f'{" " * 4}- Skipping Org: {kwargs.org}; Profile Activation for `{e}`.  No Pending Changes.')
        return kwargs

    # =========================================================================
    # Function - Server Profile Identity Reservations
    # =========================================================================
    def profiles_server_identity_reservations(self, kwargs):
        # =====================================================================
        # Send Begin Notification and Load Variables
        # =====================================================================
        pcolor.LightGray(f'  {"-" * 60}\n')
        pcolor.LightPurple(
            '   Beginning Server Profile Pool Reservations Deployments\n')
        # =====================================================================
        # Obtain Pool Names
        # =====================================================================
        np, ns = self.name_prefix_suffix(kwargs.org, kwargs)
        kwargs.cpools = DotMap()
        for item in kwargs.resources:
            if item.get('reservations') and not item.get(
                    'ignore_reservations', False):
                for i in item.reservations:
                    pool_name = i.get('pool_name', '')
                    ptype = str(i.get('identity_type', '')).lower()
                    if pool_name and ptype:
                        org, pool = pool_name.split('/')
                        pentry = kwargs.intersight_api.get(
                            org,
                            {}).get(
                            'pools',
                            {}).get(
                            ptype,
                            {}).get(pool)
                        if not pentry:
                            pcolor.Yellow(
                                f'  * Skipping Org: {kwargs.org}; Pool `{pool_name}` ({ptype}) not found for reservation lookup.')
                            continue
                        pmoid = pentry.moid
                        if not kwargs.cpools.get(ptype):
                            kwargs.cpools[ptype] = []
                        kwargs.cpools[ptype].append(pmoid)
        # =====================================================================
        # Get Identity Leases & Reservations
        # =====================================================================
        for k, v in kwargs.cpools.items():
            if v:
                names = list(set(v))
                kwargs = configure(
                    category='pools', type=f'{k}.leases').api_get(
                    True, names, f'{k}.leases', kwargs)
                kwargs = configure(
                    category='pools', type=f'{k}.reservations').api_get(
                    True, names, f'{k}.reservations', kwargs)
        # =====================================================================
        # Build Identity Reservations api_body
        # =====================================================================

        def get_ip_type(identity):
            return 'IPv6' if ':' in identity else 'IPv4'

        def build_api_body(item, e, kwargs):
            org, pool = e.pool_name.split('/')
            ptype = str(e.identity_type).lower()
            pdata = kwargs.intersight_api[org].pools[ptype][pool]
            leases = pdata.get('lease', {}) if pdata.get('lease') else {}
            profile = f'{np}{item.name}{ns}'
            reservations = pdata.get(
                'reservation', {}) if pdata.get('reservation') else {}
            if e.identity not in leases.keys():
                if e.identity not in reservations.keys():
                    org, pool = e.pool_name.split('/')
                    pdata = kwargs.intersight_api[org].pools[ptype][pool].result
                    api_body = {
                        'Identity': e.identity,
                        'Pool': {
                            'Moid': pdata.Moid,
                            'ObjectType': pdata.ObjectType}}
                    if re.search('wwnn|wwpn', ptype):
                        api_body['IdPurpose'] = ptype.upper()
                    api_body = self.profiles_org_map(
                        api_body, kwargs.org_moids[org].moid)
                    if 'ip' == ptype:
                        api_body.update({'IpType': get_ip_type(e.identity)})
                    if not bulk_list.get(ptype):
                        bulk_list[ptype] = []
                    bulk_list[ptype].append(api_body)
                else:
                    existing_reservation_moid = reservations[e.identity].moid
                    pcolor.Cyan(
                        f"  * Skipping Org: {kwargs.org} > Server Profile: `{profile}` > {ptype.upper()} Reservation: {e.identity}. "
                        f"Existing reservation: {existing_reservation_moid}")
            else:
                entity = leases[e.identity].result['AssignedToEntity']
                pcolor.Yellow(
                    f"  * NOTIFICATION: Org: {kwargs.org} > Server Profile: `{profile}` > {ptype.upper()} Reservation: {e.identity}. "
                    f"Currently leased to {entity['ObjectType']} - Moid: {entity['Moid']}")
            return kwargs
        bulk_list = DotMap()
        for item in kwargs.resources:
            if item.reservations:
                for e in item.reservations:
                    kwargs = build_api_body(item, e, kwargs)
        # =====================================================================
        # POST Bulk Request if Post List > 0
        # =====================================================================
        for k, v in bulk_list.items():
            if v:
                kwargs.bulk_list = v
                kwargs.uri = kwargs.ezdata[f'intersight.pools.{k}.reservations']['x-intersight-uri']
                kwargs = configure(
                    category='pools',
                    type=self.type).create_bulk_request(kwargs)
        # =====================================================================
        # Send End Notification and return kwargs
        # =====================================================================
        pcolor.LightPurple('\n    Completed Pool Reservations Deployments\n')
        pcolor.LightGray(f'  {"-" * 60}\n')
        return kwargs

    # =========================================================================
    # Function - Build Server Profile Reservations
    # =========================================================================
    def profiles_server_reservations(self, e, api_body, kwargs):
        for i in e.reservations:
            org, pool = i.pool_name.split('/')
            ptype = str(i.identity_type).lower()
            pdata = kwargs.intersight_api[org].pools[ptype][pool]
            rkeys = list(pdata.get('reservation', {}).keys()
                         ) if pdata.get('reservation') else []
            if i.identity in rkeys:
                if not api_body.get('ReservationReferences'):
                    api_body['ReservationReferences'] = []
                rdata = pdata.reservation[i.identity].result
                if 'ww' in ptype:
                    rdict = {'ObjectType': 'fcpool.ReservationReference'}
                else:
                    rdict = {'ObjectType': f'{ptype}pool.ReservationReference'}
                rdict.update({'ReservationMoid': rdata.Moid})
                if re.search('ip|mac|wwnn|wwpn', ptype):
                    if 'ip' in ptype and i.get('ip_usage', '') == 'Management':
                        if ':' in i.identity:
                            rdict.update({'ConsumerType': 'InbandIpv6-Access'})
                        else:
                            mgmt_type = str(
                                i.get(
                                    'management_type',
                                    'Inband')).lower().capitalize()
                            rdict.update(
                                {'ConsumerType': f'{mgmt_type}Ipv4-Access'})
                    elif i.get('ip_usage', '') == 'iSCSI':
                        rdict.update(
                            {'ConsumerName': i.interface, 'ConsumerType': 'ISCSI'})
                    elif 'mac' in ptype:
                        rdict.update(
                            {'ConsumerName': i.interface, 'ConsumerType': 'Vnic'})
                    elif 'wwpn' in ptype:
                        rdict.update(
                            {'ConsumerName': i.interface, 'ConsumerType': 'Vhba'})
                    elif 'wwnn' in ptype:
                        rdict.update({'ConsumerType': 'WWNN'})
                api_body['ReservationReferences'].append(rdict)
            else:
                pcolor.Yellow(
                    f"  * NOTIFICATION: Reservation identity `{i.identity}` not found in pool `{i.pool_name}` ({ptype}).")
        return api_body

    # =========================================================================
    # Function - Profiles Merge Defined Templates
    # =========================================================================
    def profiles_template_lookup(self, template_type, kwargs):
        ptitle = notifications.mod_pol_description(
            (self.type.replace('_', ' ').title()))
        kwargs.templates = DotMap()
        orgs = set()
        template_success = True
        template_cfg = configure(category='templates', type=self.type)
        for e in kwargs.resources:
            if template_type in e and e.get(template_type) is not None:
                template_org, template_name = template_cfg.determine_resource_organization(
                    False, e[template_type], kwargs)
                orgs.add(template_org)
                templates = kwargs.imm_templates[template_org].templates[self.type]
                if template_name in templates:
                    kwargs.templates[template_org][template_name] = kwargs.imm_templates[template_org].templates[self.type][template_name]
                else:
                    kwargs.templates[template_org][template_name] = DotMap()
                    template_success = False
        if not template_success and orgs:
            template_results = []
            if re.search('domain|unified_edge', self.type):
                ttype = 'domain.switch'
            else:
                ttype = self.type
            template_cfg = configure(category='templates', type=ttype)
            for org in orgs:
                if ttype == 'domain.switch':
                    names = [f'{e}-{suffix}' for e in kwargs.templates[org].keys()
                             for suffix in ['A', 'B'] if len(e.toDict()) == 0]
                else:
                    names = [
                        e for e in kwargs.templates[org].keys() if len(
                            e.toDict()) == 0]
                if len(names) > 0:
                    kwargs = template_cfg.api_get(
                        False, [kwargs.templates[org].keys()], ttype, kwargs)
                    kwargs.intersight_policies = DotMap()
                    kwargs.intersight_pools = DotMap()
                    for e in kwargs.results:
                        template_results.append(e)
                        for p in e.PolicyBucket:
                            ptype = kwargs.intersight_object_map[p.ObjectType]
                            kwargs.policies.setdefault(ptype, DotMap())
                            if p.Moid in kwargs.policies[ptype]:
                                continue
                            kwargs.intersight_policies.setdefault(ptype, [])
                            if p.Moid not in kwargs.intersight_policies[ptype]:
                                kwargs.intersight_policies[ptype].append(
                                    p.Moid)
                        if e.get('UuidPool'):
                            kwargs.pools.setdefault('uuid', DotMap())
                            if e.UuidPool.Moid in kwargs.pools['uuid']:
                                continue
                            kwargs.intersight_pools.setdefault('uuid', [])
                            if e.UuidPool.Moid not in kwargs.intersight_pools['uuid']:
                                kwargs.intersight_pools['uuid'].append(
                                    e.UuidPool.Moid)
            policies_cfg = api(category='policies', type='moid_filter')
            for k, v in kwargs.intersight_policies.items():
                if v:
                    uri = kwargs.ezdata[f'intersight.policies.{k}']['x-intersight-uri']
                    kwargs = kwargs | DotMap(method='get', names=v, uri=uri)
                    kwargs = policies_cfg.calls(kwargs)
                    for e in kwargs.results:
                        kwargs.policies[k][e.Moid] = DotMap(
                            name=e.Name, organization=kwargs.org_names[e.Organization.Moid])
            if kwargs.intersight_pools.get('uuid'):
                uri = kwargs.ezdata['intersight.pools.uuid']['x-intersight-uri']
                kwargs = kwargs | DotMap(
                    method='get', names=kwargs.pools['uuid'], uri=uri)
                kwargs = api(
                    category='pools',
                    type='moid_filter').calls(kwargs)
                for e in kwargs.results:
                    kwargs.pools[k][e.Moid] = DotMap(  # pylint: disable=undefined-loop-variable
                        name=e.Name, organization=kwargs.org_names[e.Organization.Moid])
            for e in template_results:
                name = e.get('Name', '')
                organization = kwargs.org_names[e.Organization.Moid]
                if e.get('UuidPool'):
                    pref = kwargs.pools['uuid'][e.UuidPool.Moid]
                    kwargs.templates[organization][
                        name].uuid_pool = f'{kwargs.org_names[pref.Organization.Moid]}/{pref.Name}'
                for p in e.PolicyBucket:
                    ptype = kwargs.intersight_object_map[p.ObjectType]
                    pref = kwargs.policies[ptype][p.Moid]
                    kwargs.templates[organization][name][
                        f'{ptype}_policy'] = f'{kwargs.org_names[pref.Organization.Moid]}/{pref.Name}'
            if ttype == 'domain.switch':
                policy_keys = {'port_policy', 'vlan_policy', 'vsan_policy'}
                for org in orgs:
                    templates = [
                        e for e in kwargs.templates[org].keys() if len(
                            kwargs.templates[org][e].toDict()) == 0 and re.search(
                            '-A$', e)]
                    for template in templates:
                        tname = re.sub(
                            "-A$", "", template, flags=re.IGNORECASE)
                        kwargs.templates[org][tname] = DotMap()
                        for suffix in ['A', 'B']:
                            for k, v in kwargs.templates[org][f'{template}-{suffix}'].items(
                            ):
                                if k.endswith(
                                        '_policy') or k.endswith('_pool'):
                                    if k in policy_keys:
                                        plural_type = k.replace(
                                            '_policy', '_policies')
                                        if not kwargs.templates[org][tname].get(
                                                plural_type, None):
                                            kwargs.templates[org][tname][plural_type] = [
                                            ]
                                        if v not in kwargs.templates[org][tname][plural_type]:
                                            kwargs.templates[org][tname][plural_type].append(
                                                v)
                                    elif not kwargs.templates[org][tname].get(k, None):
                                        kwargs.templates[org][tname][k] = v
        final_check = True
        for org in orgs:
            templates = list(kwargs.templates[org].keys())
            for template in templates:
                if len(kwargs.templates[org][template].toDict()) == 0:
                    final_check = False
                    pcolor.Red(
                        f'!!! ERROR !!! {ptitle} Template(s) "{", ".join(templates)}" were not found under Organization "{org}".')
                    pcolor.Red(
                        f'Available templates in Organization `{org}` are: {", ".join(sorted(templates))}')
        if not final_check:
            raise ValueError(
                f'{ptitle} template validation failed for one or more organizations')
        return kwargs

    # =========================================================================
    # Function - Profiles Merge Defined Templates
    # =========================================================================
    def profiles_template_merge(self, item, template_name, ptitle, kwargs):
        org, name = template_name.split('/')
        templates = kwargs.templates[org]
        if name in templates:
            merged = self.deep_merge_dicts(
                deepcopy(templates[name].toDict()), item.toDict())
        else:
            pcolor.Red(
                f'!!! ERROR !!! {ptitle} Template "{template_name}" was not found.')
            pcolor.Red(
                f'Available templates in Organization `{org}` are: {", ".join(sorted(templates.keys()))}')
            raise ValueError(
                f'{ptitle} template "{template_name}" was not found')
        return DotMap(merged)

    # =========================================================================
    # Function - Server Profiles/Templates Updates
    # =========================================================================
    def profiles_templates_create_policy_bucket(self, item, kwargs):
        ikeys = list(item.keys())

        chassis_ = [
            'imc_access_policy',
            'power_policy',
            'snmp_policy',
            'thermal_policy']
        domain_ = [
            'auditd_policy',
            'certificate_management_policy',
            'ldap_policy',
            'netflow_configuration_policy',
            'network_connectivity_policy',
            'ntp_policy',
            'port_policy',
            'snmp_policy',
            'switch_control_policy',
            'syslog_policy',
            'system_qos_policy',
            'vlan_policy',
            'vsan_policy']
        fi_only = [
            'drive_security_policy',
            'pcie_connectivity_policy',
            'san_connectivity_policy',
            'sd_card_policy',
            'thermal_policy']
        fi_unified_common = [
            'bios_policy',
            'boot_order_policy',
            'certificate_management_policy',
            'firmware_policy',
            'imc_access_policy',
            'ipmi_over_lan_policy',
            'lan_connectivity_policy',
            'local_user_policy',
            'memory_policy',
            'power_policy',
            'scrub_policy',
            'serial_over_lan_policy',
            'snmp_policy',
            'storage_policy',
            'syslog_policy',
            'virtual_kvm_policy',
            'virtual_media_policy']
        standalone_common = [
            'bios_policy',
            'certificate_management_policy',
            'firmware_policy',
            'ipmi_over_lan_policy',
            'local_user_policy',
            'power_policy',
            'serial_over_lan_policy',
            'smtp_policy',
            'ssh_policy',
            'virtual_kvm_policy',
            'virtual_media_policy',
        ]
        standalone_2xx_4xx_only = [
            'boot_order_policy',
            'memory_policy',
            'persistent_memory_policy',
            'thermal_policy',
            'device_connector_policy',
            'ldap_policy',
            'network_connectivity_policy',
            'ntp_policy',
            'snmp_policy',
            'syslog_policy',
            'drive_security_policy',
            'sd_card_policy',
            'storage_policy',
            'adapter_configuration_policy',
            'lan_connectivity_policy',
            'san_connectivity_policy']
        unified_edge_ = [
            'power_policy',
            'thermal_policy',
            'port_policy',
            'switch_control_policy',
            'system_qos_policy',
            'vlan_policy',
            'local_user_policy',
            'network_connectivity_policy',
            'ntp_policy',
            'syslog_policy']
        target_platform = item.get('target_platform', 'FIAttached')
        server_family = item.get('server_family', 'All')

        if self.type == 'chassis' or target_platform == 'Chassis':
            allowed_policies = chassis_
        elif self.type == 'domain' or target_platform == 'UCS Domain':
            allowed_policies = domain_
        elif self.type == 'unified_edge' or target_platform == 'Unified Edge':
            allowed_policies = unified_edge_
        elif target_platform == 'FIAttached':
            allowed_policies = fi_unified_common + fi_only
        elif target_platform == 'UnifiedEdgeServer':
            allowed_policies = fi_unified_common
        elif target_platform == 'Standalone':
            if server_family == 'UCSC845A':
                allowed_policies = standalone_common
            elif server_family == 'UCSC2XX/4XX':
                allowed_policies = standalone_common + standalone_2xx_4xx_only
            else:
                allowed_policies = standalone_common + standalone_2xx_4xx_only
        else:
            allowed_policies = fi_unified_common + fi_only
        item.allowed_policies = list(dict.fromkeys(allowed_policies))
        item.policy_bucket = DotMap()

        # Find policy keys from input item, excluding internal control
        # attributes
        internal_keys = {
            'allowed_policies',
            'policy_bucket',
            'object_map',
            'target_platform',
            'server_family'}
        policy_like_keys = [k for k in ikeys if k.endswith(
            '_policy') and item.get(k) and k not in internal_keys]
        allowed_input_keys = set(item.allowed_policies)
        skipped = [k for k in policy_like_keys if k not in allowed_input_keys]
        if len(skipped) > 0:
            message_title = f'{target_platform}/{server_family}' if self.type == 'server' else f'{target_platform.title()}'
            pcolor.Yellow(
                f"  * Skipping unsupported template policies for `{item.name}` ({message_title}): "
                f"{', '.join(sorted(skipped))}")
        # Attach Allowed Policies to policy_bucket for downstream processing
        # and API body construction.
        for key in item.allowed_policies:
            if key in ikeys and item.get(key):
                item.policy_bucket[key] = item[key]
        item.object_map = kwargs.intersight_object_map
        return item

    # =========================================================================
    # Function - Domain/Unified Edge Profiles/Templates Updates
    # =========================================================================
    def profiles_templates_domain_unified_edge(self, kwargs):
        kwargs.merge_templates = DotMap()
        ptitle = notifications.mod_pol_description(
            (self.type.replace('_', ' ').title()))
        serials = []
        names = []
        org = kwargs.org
        np, ns = self.name_prefix_suffix(org, kwargs)
        if self.type == 'unified_edge':
            target_platform = 'Unified Edge'
        else:
            target_platform = 'UCS Domain'
        template_type = f'{target_platform.lower().replace(" ", "_")}_profile_template'
        template_check = False
        resources = deepcopy(kwargs.resources)
        for e in resources:
            ekeys = list(e.keys())
            if self.category == 'profiles':
                if 'serial_numbers' in ekeys:
                    remove_count = 0
                    for s in e.serial_numbers:
                        if re.search(serial_regex, s):
                            serials.append(s)
                        else:
                            remove_count += 1
                            pcolor.Yellow(
                                f'!!! WARNING !!! Serial number "{s}" does not match expected format and will be skipped for profile "{e.name}".')
                    if remove_count > 0:
                        kwargs.resources[kwargs.resources.index(
                            e)].serial_numbers = []
                elif 'serial_number' in ekeys:
                    if re.search(serial_regex, e.serial_number):
                        serials.append(e.serial_number)
                    else:
                        kwargs.resources[kwargs.resources.index(
                            e)].serial_number = None
                        pcolor.Yellow(
                            f'!!! WARNING !!! Serial number "{e.serial_number}" does not match expected format and will be skipped for profile "{e.name}".')
                if self.category == 'profiles' and e.get(
                        template_type, None) is not None and e.get(
                        'attach_template', True) is False:
                    template_check = True
            names.append(f'{np}{e.name}{ns}')
        if template_check:
            kwargs = self.profiles_template_lookup(template_type, kwargs)
        if len(serials) > 0:
            kwargs = system(
                category='system',
                type=self.type).api_get(
                True,
                serials,
                kwargs)
        kwargs.org = org
        kwargs = self.api_get(True, names, self.type, kwargs)
        domain_cfg = configure(category=self.category, type='domain')
        switch_cfg = configure(category=self.category, type='domain.switch')
        pdict = kwargs.intersight_api[org][self.category].domain
        kwargs = switch_cfg.api_get(
            True, [pdict[e].moid for e in names if e in pdict], 'domain.switch', kwargs)
        # =====================================================================
        # Domain/Unified Edge Profile API Body Creation and Comparison Loop.
        # If Differences or No Existing Resource, Append to Bulk List for POST/PATCH.  If No Differences, Skip.
        # =====================================================================
        kwargs.bulk_list = []
        for item in kwargs.resources:
            item.target_platform = self.type.replace('_', ' ').title()
            api_body = domain_cfg.create_api_body(item, np, ns, kwargs)
            kwargs = domain_cfg.compare_resources_to_api(
                api_body, ptitle, kwargs)
        # POST Bulk Request if List > 0
        if len(kwargs.bulk_list) > 0:
            kwargs.uri = kwargs.ezdata[f"intersight.{self.category}.domain"]['x-intersight-uri']
            kwargs = domain_cfg.create_bulk_request(kwargs)
        # =====================================================================
        # Domain/Unified Edge Switch Profile API Body Creation and Comparison Loop.
        # If Differences or No Existing Resource, Append to Bulk List for POST/PATCH.  If No Differences, Skip.
        # =====================================================================
        policies = ['port_policies', 'vlan_policies', 'vsan_policies']
        policy_singular = {
            p: p.replace(
                '_policies',
                '_policy') for p in policies}
        kwargs.bulk_list = []
        for item in kwargs.resources:
            item.name = f"{np}{item.name}{ns}"
            item.parent = kwargs.intersight_api[org][self.category].domain[item.name].moid
            item.target_platform = target_platform
            if self.category == 'profiles' and item.get(
                    'attach_template', True) is False and item.get(
                    template_type, None) is not None:
                item = self.profiles_template_merge(
                    item, item[template_type], ptitle, kwargs)
            i_orginal = deepcopy(item)
            for s in ['A', 'B']:
                item = deepcopy(i_orginal)
                item.index = ord(s) - 65
                item.switch_id = s
                for p in policies:
                    if p in item:
                        item[policy_singular[p]] = item[p][item.index] if len(
                            item[p]) > 1 else item[p][0]
                        item.pop(p)
                item = self.profiles_templates_create_policy_bucket(
                    item, kwargs)
                api_body = switch_cfg.create_api_body(item, np, ns, kwargs)
                kwargs = switch_cfg.children_compare_api_body(api_body, kwargs)
        # POST Bulk Request if List > 0
        if len(kwargs.bulk_list) > 0:
            kwargs.uri = kwargs.ezdata[f"intersight.{self.category}.domain.switch"]['x-intersight-uri']
            kwargs = switch_cfg.create_bulk_request(kwargs)
        return kwargs

    # =========================================================================
    # Function - Unified Edge Profiles Updates
    # =========================================================================
    def profiles_unified_edge(self, kwargs):
        kwargs = self.profiles_templates_domain_unified_edge(kwargs)
        return kwargs

    # =========================================================================
    # Function - Chassis Templates Updates
    # =========================================================================
    def templates_chassis(self, item, kwargs):
        item = self.profiles_templates_create_policy_bucket(item, kwargs)
        return item

    # =========================================================================
    # Function - Domain Templates Updates
    # =========================================================================
    def templates_domain(self, kwargs):
        kwargs = self.profiles_templates_domain_unified_edge(kwargs)
        return kwargs

    # =========================================================================
    # Function - Server Templates Updates
    # =========================================================================
    def templates_server(self, item, kwargs):
        item = self.profiles_templates_create_policy_bucket(item, kwargs)
        return item

    # =========================================================================
    # Function - Unified Edge Templates Updates
    # =========================================================================
    def templates_unified_edge(self, kwargs):
        kwargs = self.profiles_templates_domain_unified_edge(kwargs)
        return kwargs
