"""Intersight initialize class."""
# Copyright (c) 2026 Cisco Systems, Inc. and its affiliates.
# All rights reserved.
# pylint: disable=invalid-name,missing-class-docstring,missing-function-docstring
# pylint: disable=too-many-branches,too-many-statements,too-many-locals
# pylint: disable=too-many-nested-blocks,too-few-public-methods
# =============================================================================
# Source Modules
# =============================================================================
import sys
from pathlib import Path


def prRed(skk):
    print(f"\033[91m {skk}\033[00m")


SCRIPT_PATH = Path(__file__).resolve().parent
CLASSES_PATH = SCRIPT_PATH / 'src'
REPO_ROOT = SCRIPT_PATH.parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_PATH) not in sys.path:
    sys.path.insert(1, str(SCRIPT_PATH))
if str(CLASSES_PATH) not in sys.path:
    sys.path.insert(2, str(CLASSES_PATH))

try:
    from roles.intersight_ucs_provision.library.src import bmc
    from roles.intersight_ucs_provision.library.src import pcolor
    from roles.intersight_ucs_provision.library.src.intersight.api import api
    from roles.intersight_ucs_provision.library.src.intersight.configure import configure
    from roles.intersight_ucs_provision.library.src.intersight.system import system
    import re
except ImportError as e:
    prRed(
        f'src/intersight/functions_to_run.py - !!! ERROR !!!\n{e.__class__.__name__}')
    prRed(f" Module {e.name} is required to run this script")
    prRed(f" Install the module using the following: `pip install {e.name}`")
    sys.exit(1)

# =============================================================================
# Intersight -> Initialize Intersight Classes
# =============================================================================


class begin:
    def __init__(self, category=None, type=None):  # pylint: disable=redefined-builtin
        self.category = category
        self.type = type

    # =========================================================================
    # Function: Define Initialize Functions to Run
    # =========================================================================
    def functions_to_run(self, kwargs):
        if not kwargs.get('imm_dict') or not kwargs.imm_dict.get('orgs'):
            raise ValueError(
                'No organizations were found in the loaded configuration (missing `imm_dict.orgs`)')
        kwargs.orgs = list(kwargs.imm_dict.orgs.keys())
        if len(kwargs.orgs) > 0:
            kwargs = api(
                category='system',
                type='organizations').all_organizations(kwargs)
        else:
            pcolor.Yellow(f'{"-" * 108}')
            pcolor.Yellow(
                '   No Organizations found in the YAML configuration files.')
            pcolor.Yellow(
                '   Confirm that you have created the YAML configuration files correctly and that they contain at least one organization with configurations.')
            pcolor.Yellow(f'{"-" * 108}')
            raise ValueError(
                'No organizations found in YAML configuration files')
        # =====================================================================
        # Build Lists from ezdata
        # =====================================================================
        kwargs.policies_list = []
        kwargs.pools_list = []
        kwargs.profiles_list = []
        kwargs.templates_list = []
        kwargs.system_list = []
        category_regex = re.compile(
            r'intersight\.(policies|pools|profiles|system|templates)\.',
            re.IGNORECASE)
        for k, v in kwargs.ezdata.items():
            match = category_regex.search(k)
            if match:
                rtype = match.group(1)
                r = category_regex.sub('', k)
                if '.' not in r and v.get('x-intersight-object-type'):
                    kwargs[f'{rtype}_list'].append(r)
        if 'switch' in kwargs.profiles_list:
            kwargs.profiles_list.remove('switch')
        if 'switch' in kwargs.templates_list:
            kwargs.templates_list.remove('switch')
        iboot_index = kwargs.policies_list.index(
            'iscsi_boot') if 'iscsi_boot' in kwargs.policies_list else len(kwargs.policies_list)
        ip_index = kwargs.pools_list.index(
            'ip') if 'ip' in kwargs.pools_list else len(kwargs.pools_list)
        ptemplates = ['id_mapping', 'server_pool_qualification']
        vtemplates = ['vnic_template', 'vhba_template']
        for e in ['iscsi_static_target'] + vtemplates:
            if e in kwargs.templates_list:
                kwargs.templates_list.remove(e)
                kwargs.policies_list.insert(iboot_index, e)
            elif e in kwargs.policies_list:
                kwargs.policies_list.remove(e)
                kwargs.policies_list.insert(iboot_index, e)
                iboot_index += 1
        if 'resource_groups' in kwargs.system_list:
            kwargs.system_list.remove('resource_groups')
            kwargs.system_list.insert(0, 'resource_groups')
        for e in ptemplates:
            if e in kwargs.policies_list:
                kwargs.policies_list.remove(e)
                kwargs.pools_list.insert(ip_index, e)
                ip_index += 1
        # =====================================================================
        # Pools/Policies/Profiles/Templates
        # =====================================================================
        kkeys = list(kwargs.imm_dict)
        if 'system' in kkeys:
            for ptype in kwargs.system_list:
                kwargs.org = 'default'
                if ptype in kwargs.imm_dict.get('system', {}):
                    kwargs = system(
                        category='system',
                        type=f'{ptype}').system(kwargs)
        for e in ['pools', 'policies', 'templates', 'profiles']:
            for ptype in kwargs[f'{e}_list']:
                for org in kwargs.orgs:
                    kwargs.org = org
                    category = 'policies' if ptype in ptemplates else 'templates' if ptype in vtemplates else e
                    if ptype in kwargs.imm_dict.orgs[org].get(category, {}):
                        if category == 'profiles' and ptype == 'server':
                            for item in kwargs.imm_dict.orgs[org].get(
                                    category, {}).get(ptype, []):
                                if item.get('server_family') == 'UCSC885A':
                                    kwargs.resources = item
                                    kwargs = bmc.build(
                                        category='server', type=item.get('server_family')).configure_server(kwargs)
                        kwargs = configure(
                            category=category, type=ptype).configure(kwargs)
        # =====================================================================
        # return kwargs
        # =====================================================================
        return kwargs
