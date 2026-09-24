"""Intersight system class."""
# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates.
# All rights reserved.
# pylint: disable=invalid-name,missing-class-docstring,missing-function-docstring
# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-nested-blocks,import-outside-toplevel
# =============================================================================
# Source Modules
# =============================================================================
import sys
from .. import notifications


def prRed(skk):  # pylint: disable=invalid-name
    print(f"\033[91m {skk}\033[00m")


try:
    from .. import pcolor
    from .api import api
    from copy import deepcopy
    from dotmap import DotMap
    import jinja2
    import json
    import numpy
    import os
    import re
except ImportError as e:
    prRed(f'src/intersight/system.py - !!! ERROR !!!\n{e.__class__.__name__}')
    prRed(f" Module {e.name} is required to run this script")
    prRed(f" Install the module using the following: `pip install {e.name}`")
    sys.exit(1)

# Lazy imports to resolve cross-module class references


def configure(*args, **kwargs):
    from .configure import configure as _configure
    return _configure(*args, **kwargs)


# =============================================================================
# Intersight -> System Class
# =============================================================================
class system:
    def __init__(self, category=None, type=None):  # pylint: disable=redefined-builtin
        self.category = category
        self.type = type

    # =========================================================================
    # Function - API Get Calls
    # =========================================================================
    def api_get(self, empty=False, names=None, kwargs=None):
        if names is None:
            names = []
        if kwargs is None:
            kwargs = DotMap()
        # =====================================================================
        # Function - Exit on Empty Results
        # =====================================================================

        def empty_results(names, kwargs):
            pcolor.Red(f"The API Query Results were empty for {kwargs.uri}.")
            pcolor.Red(f"  Names: `{', '.join(names)}`")
            pcolor.Red("Exiting...")
            sys.exit(1)
        if re.search(r'^(blades|rackmounts)$', self.type):
            kwargs = kwargs | DotMap(
                names=names,
                method='get',
                uri='compute/PhysicalSummaries')
        elif 'iam_sharing_rules' == self.type:
            kwargs = kwargs | DotMap(
                names=names, method='get', uri='iam/SharingRules')
        elif 'targets' == self.type:
            kwargs = kwargs | DotMap(
                names=names, method='get', uri='asset/Targets')
        else:
            uri = kwargs.ezdata[f"intersight.{self.category}.{self.type}"]['x-intersight-uri']
            kwargs = kwargs | DotMap(
                names=names, org='default', method='get', uri=uri)
        kwargs = api(category=self.category, type=self.type).calls(kwargs)
        if not empty and kwargs.results == []:
            empty_results(names, kwargs)
        elif empty and kwargs.results == []:
            pcolor.Yellow(f"  * API Query Results were empty for {kwargs.uri}")
            pcolor.Yellow(f"    - Names: `{', '.join(names)}`.  Continuing...")
        return kwargs

    # =========================================================================
    # Function - Create API Request Body
    # =========================================================================
    def create_api_body(self, item, kwargs):
        if re.fullmatch('resource_groups', self.type):
            item = getattr(self, self.type)(item, kwargs)
        item = configure(
            category=self.category,
            type=self.type).merge_tags(
            item,
            kwargs)

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
            object_map=kwargs.intersight_object_map,
            org_moids=kwargs.org_moids,
            rsg_moids=kwargs.rsg_moids
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
            len(False)
            sys.exit(1)
        return api_body

    # =========================================================================
    # Function - Check if System Sub Attributes Exist Already
    # =========================================================================
    def existing_check(self, reconcile_resources, kwargs):
        kwargs.cp = DotMap()

        def register_cp_name(resource_type, name):
            if not kwargs.cp.get(resource_type):
                kwargs.cp[resource_type] = DotMap(names=[], category='system')
            if name not in kwargs.cp[resource_type].names:
                kwargs.cp[resource_type].names.append(name)

        for item in reconcile_resources:
            if self.type == 'organizations' and isinstance(
                    item.get('resource_groups'), list):
                for rg in item.resource_groups:
                    register_cp_name('resource_groups', rg)
            elif self.type == 'resource_groups' and isinstance(item.get('resources'), dict):
                if isinstance(item.resources.get('targets'), list):
                    for target in item.resources['targets']:
                        register_cp_name('targets', target)
                if isinstance(item.resources.get('sub_targets'), dict):
                    for e in ['blades', 'rackmounts']:
                        if isinstance(
                                item.resources['sub_targets'].get(e), list):
                            for target in item.resources['sub_targets'][e]:
                                register_cp_name(e, target)
        return reconcile_resources, kwargs

    # =========================================================================
    # Function - Get Organizations from Intersight
    # =========================================================================
    def organizations(self, kwargs):
        kwargs.bulk_list = []
        names = []
        # =====================================================================
        # Function to Create Resource Groups and Organizations
        # =====================================================================

        def compare_to_api(api_body, check_flag, kwargs):
            check_count = False
            org = kwargs.org_names[api_body['SharedWithResource']['Moid']]
            shared_org = kwargs.org_names[api_body['SharedResource']['Moid']]
            for k, v in kwargs.intersight_api.system.iam_sharing_rules.items():
                if v.result.SharedResource.Moid == api_body['SharedResource'][
                        'Moid'] and v.result.SharedWithResource.Moid == api_body['SharedWithResource']['Moid']:
                    pcolor.Cyan(
                        f"     * Skipping System -> IAM Sharing Rule: Moid - `{k}`.  Intersight Matches Configuration. "
                        f"Shared Resource: `{shared_org}` -> Shared With: `{org}`")
                    check_count = True
                    break
            if not check_count:
                if check_flag:
                    shared_org = kwargs.org_names[api_body['SharedResource']['Moid']]
                    org = kwargs.org_names[api_body['SharedWithResource']['Moid']]
                    pcolor.Cyan(
                        f"     * Running Check Mode: Non-Check mode would create new System -> IAM Sharing Rule: "
                        f"Shared Resource: `{shared_org}` -> Shared With: `{org}`.")
                else:
                    kwargs.bulk_list.append(deepcopy(api_body))
            return kwargs
        # =====================================================================
        # Function Determine if there are Shared Orgs
        # =====================================================================
        for e in kwargs.resources:
            ekeys = list(e.keys())
            if 'organizations_to_share_with' in ekeys:
                names.extend(e['organizations_to_share_with'])
        names = list(numpy.unique(numpy.array(names)))
        # =====================================================================
        # Function Loop over Shared Orgs if they are defined.
        # =====================================================================
        if len(names) > 0:
            kwargs = kwargs | DotMap(
                names=names,
                method='get',
                uri='organization/Organizations')
            kwargs = self.api_get(empty=False, names=names, kwargs=kwargs)
            odict = kwargs.intersight_api.system.organizations
            names = [odict.get(e.name).moid for e in kwargs.resources if e.get(
                'organizations_to_share_with') is not None and len(e.organizations_to_share_with) > 0]
            kwargs = system(
                category=self.category,
                type='iam_sharing_rules').api_get(
                empty=False,
                names=names,
                kwargs=kwargs)
            for item in kwargs.resources:
                for e in item.organizations_to_share_with:
                    i = DotMap(name=item.name, shared_with=e)
                    api_body = system(
                        category=self.category,
                        type='iam_sharing_rules').create_api_body(
                        i,
                        kwargs)
                    check_flag = getattr(kwargs.args, 'check', False)
                    ikeys = list(
                        kwargs.intersight_api.system.iam_sharing_rules)
                    if len(ikeys) > 0:
                        kwargs = compare_to_api(api_body, check_flag, kwargs)
        # =====================================================================
        # POST Bulk Request if List > 0
        # =====================================================================
        if len(kwargs.bulk_list) > 0:
            kwargs.uri = 'iam/SharingRules'
            kwargs = configure(
                category=self.category,
                type=self.type).create_bulk_request(kwargs)
        return kwargs

    # =========================================================================
    # Function - Intersight API Update -> System -> Path Tags
    # =========================================================================
    def path_tags(self, rdict, kwargs):
        names = list(e.path_tag for e in rdict)
        uri = kwargs.ezdata[f'intersight.system.{self.type}']['x-intersight-uri']
        kwargs = kwargs | DotMap(method='get', names=names, uri=uri)
        kwargs = api(category=self.category, type=self.type).calls(kwargs)
        for item in rdict:
            if item.path_tag not in (kwargs.intersight_api.system.path_tags):
                api_body = self.create_api_body(item, kwargs)
                kwargs = kwargs | DotMap(
                    method='post', api_body=api_body, uri=uri)
                kwargs = api(
                    category=self.category,
                    type=self.type).calls(kwargs)
            else:
                moid = kwargs.intersight_api.system.path_tags[item.path_tag].moid
                pcolor.Cyan(
                    f"     * Skipping System; Path Tags: `{item.path_tag}` - Moid: `{moid}`.  Intersight Matches Configuration.")
            names.remove(item.path_tag)
        return kwargs

    # =========================================================================
    # Function - Get Resource Group Sub Elements
    # =========================================================================
    def resource_groups(self, item, kwargs):
        ikeys = list(item.keys())
        if 'resources' in ikeys:
            item.selectors = []
            rkeys = list(item.resources.keys())
            if 'targets' in rkeys and len(item.resources.targets) > 0:
                targets = [
                    kwargs.intersight_api.system.targets[e].moid for e in item.resources.targets]
                if len(targets) == 1:
                    item.selectors.append(
                        f"/api/v1/asset/DeviceRegistrations?$filter=Moid in ('{targets[0]}')")
                else:
                    moid_list = "', '".join(targets)
                    item.selectors.append(
                        f"/api/v1/asset/DeviceRegistrations?$filter=(Moid in ('{moid_list}'))")
            if 'sub_targets' in rkeys:
                for e in ['blades', 'rackmounts']:
                    if e in item.resources.sub_targets and len(
                            item.resources.sub_targets[e]) > 0:
                        sub_targets = [
                            kwargs.intersight_api.system[e][t].moid for t in item.resources.sub_targets[e]]
                        if e == 'blades':
                            stype = 'Blades'
                        else:
                            stype = 'RackUnits'
                        moid_list = "', '".join(sub_targets)
                        item.selectors.append(
                            f"/api/v1/compute/{stype}?$filter=Serial in ('{moid_list}')")
        return item

    # =========================================================================
    # Function - Compare Intersight API to IMM Dictionary `system`
    # =========================================================================
    def system(self, kwargs):
        # =====================================================================
        # Send Begin Notification and Load Variables
        # =====================================================================
        ptitle = notifications.mod_pol_description(
            self.type.replace('_', ' ').title())
        notifications.section_begin(self.category, self.type)
        pcolor.LightGray('')
        kwargs.idata = DotMap(
            dict(
                pair for d in kwargs.ezdata[f"intersight.{self.category}.{self.type}"].allOf for pair in d.properties.items()))
        rdict = deepcopy(kwargs.imm_dict[self.category][self.type])
        if self.type == 'path_tags':
            kwargs = self.path_tags(rdict, kwargs)
            notifications.section_end(self.category, self.type)
            return kwargs
        reconcile_resources = list({v.name: v for v in rdict}.values())
        # =====================================================================
        # Get Existing Resources
        # =====================================================================
        names = list(e.name for e in rdict)
        uri = kwargs.ezdata[f"intersight.{self.category}.{self.type}"]['x-intersight-uri']
        kwargs = api(
            category=self.category,
            type=self.type).calls(
            kwargs | DotMap(
                method='get',
                names=names,
                uri=uri))
        # =====================================================================
        # Validate the Sub Resources are defined or get Moids
        # =====================================================================
        if re.search(r'organizations|resource_groups', self.type):
            reconcile_resources, kwargs = self.existing_check(
                reconcile_resources, kwargs)
            for e in list(kwargs.cp.keys()):
                if len(kwargs.cp[e].names) > 0:
                    names = list(numpy.unique(numpy.array(kwargs.cp[e].names)))
                    category = kwargs.cp[e].get('category', self.category)
                    kwargs = system(
                        category=category,
                        type=e).api_get(
                        empty=False,
                        names=names,
                        kwargs=kwargs)
        # =====================================================================
        # If Modified, Patch the Resource via the Intersight API
        # =====================================================================

        def compare_resources_to_api(api_body, ptitle, kwargs):
            category = self.category.replace('_', ' ').title()
            kwargs.uri = kwargs.ezdata[f"intersight.{self.category}.{self.type}"]['x-intersight-uri']
            check_flag = getattr(kwargs.args, 'check', False)
            akeys = list(api_body.keys())
            if 'Description' in akeys and api_body['Description'] == '':
                api_body['Description'] = f"{api_body['Name']} {re.sub(r's$', '', ptitle)}."
            if api_body['Name'] in kwargs.intersight_api[self.category][self.type]:
                intersight_api = kwargs.intersight_api[self.category][self.type][api_body['Name']]
                patch_resource = configure(
                    type=self.type).compare_body_result(
                    api_body, intersight_api.result)
                api_body['pmoid'] = intersight_api.moid
                if patch_resource:
                    if check_flag:
                        pcolor.Cyan(
                            f"     * Running Check Mode: Non-Check mode would update {category} -> {ptitle}: `{api_body['Name']}`."
                            f"  Moid: `{api_body['pmoid']}`")
                    else:
                        kwargs.bulk_list.append(deepcopy(api_body))
                        kwargs.pmoids[api_body['Name']
                                      ].moid = api_body['pmoid']
                else:
                    pcolor.Cyan(
                        f"     * Skipping {category} -> {ptitle}: `{api_body['Name']}` - Moid: `{api_body['pmoid']}`.  Intersight Matches Configuration.")
            else:
                if check_flag:
                    pcolor.Cyan(
                        f"     * Running Check Mode: Non-Check mode would create new {category} -> {ptitle}: `{api_body['Name']}`.")
                else:
                    kwargs.bulk_list.append(deepcopy(api_body))
            return kwargs
        # =====================================================================
        # Loop through Resource Items
        # =====================================================================
        kwargs.bulk_list = []
        for item in reconcile_resources:
            # =============================================================
            # Construct api_body Payload
            # =============================================================
            api_body = self.create_api_body(item, kwargs)
            kwargs = compare_resources_to_api(api_body, ptitle, kwargs)
        # =====================================================================
        # POST Bulk Request if List > 0
        # =====================================================================
        if len(kwargs.bulk_list) > 0:
            kwargs.uri = kwargs.ezdata[f"intersight.{self.category}.{self.type}"]['x-intersight-uri']
            kwargs = configure(
                category=self.category,
                type=self.type).create_bulk_request(kwargs)
        # =====================================================================
        # Loop Thru Sub-Items
        # =====================================================================
        kwargs.resources = reconcile_resources
        if self.type == 'organizations':
            kwargs = getattr(self, 'organizations')(kwargs)
        # =====================================================================
        # Send End Notification and return kwargs
        # =====================================================================
        notifications.section_end(self.category, self.type)
        return kwargs

# =============================================================================
# Software Repository Class
# =============================================================================
