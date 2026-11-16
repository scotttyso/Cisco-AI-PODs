"""Notification helpers for Intersight UCS provisioning operations."""
# =============================================================================
# Source Modules
# =============================================================================
import sys
from pathlib import Path


def pr_red(skk):
    """Print text in red to stdout."""
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
    from roles.intersight_ucs_provision.library.src import pcolor
    from dotmap import DotMap
    import json
    import re
except ImportError as e:
    pr_red(f'src/validating.py line 6 - !!! ERROR !!!\n{e.__class__.__name__}')
    pr_red(f" Module {e.name} is required to run this script")
    pr_red(f" Install the module using the following: `pip install {e.name}`")
    sys.exit(1)

oregex = re.compile(
    'fabric.([a-zA-z]+(Mode|Role)|V[l|s]an)|vnic.(Eth|Fc)If|iam.EndPointUserRole|DriveGroup|Ldap(Group|Provider)')
policy_regex = re.compile(
    '(network_connectivity|ntp|port|snmp|switch_control|syslog|system_qos|vlan|vsan)')
DESCRIPTION_WORD_MAP = {
    'Fiattached': 'FIAttached',
    'Fc': 'FC',
    'Iam': 'IAM',
    'Id': 'ID',
    'Imc': 'IMC',
    'Ip': 'IP',
    'Ipmi': 'IPMI',
    'Iqn': 'IQN',
    'Iscsi': 'iSCSI',
    'Lan': 'LAN',
    'Ldap': 'LDAP',
    'Mac': 'MAC',
    'Ntp': 'NTP',
    'Policies': 'Policy',
    'Pools': 'Pool',
    'Profiles': 'Profile',
    'San': 'SAN',
    'Sd': 'SD',
    'Smtp': 'SMTP',
    'Snmp': 'SNMP',
    'Templates': 'Template',
    'Ssh': 'SSH',
    'Uuid': 'UUID',
    'Vhbas': 'vHBAs',
    'Vlan': 'VLAN',
    'Vnics': 'vNICs',
    'Vsan': 'VSAN',
    'Wwnn': 'WWNN',
    'Wwpn': 'WWPN',
}

# =============================================================================
# Function - Change Policy Description to Sentence
# =============================================================================


def mod_pol_description(pol_description):
    """Convert a policy description string from snake_case to title-case words."""
    words = str.title(pol_description.replace('_', ' ')).split()
    return ' '.join(DESCRIPTION_WORD_MAP.get(word, word) for word in words)

# =============================================================================
# Notifications
# =============================================================================


def begin_loop(ptype1, ptype2):
    """Print a section-begin banner for a deployment loop."""
    pcolor.LightGray(f'\n{"-" * 108}\n')
    pcolor.LightPurple(
        f"  Beginning {' '.join(ptype1.split('_')).title()} {ptype2} Deployment.\n")


def completed_item(category, ptype, kwargs):  # pylint: disable=too-many-branches,too-many-statements,too-many-locals
    """Print a completion notification for a single API operation."""
    iresults = DotMap(kwargs.api_results)
    ikeys = list(iresults.keys())
    method = kwargs.method
    name = None
    pmoid = iresults.Moid
    regex = re.compile(
        r'^(comm.TagDefinition|iam.SharingRule|organization.Organization|resource.Group)$',
        re.IGNORECASE)
    preg = re.compile(
        r'^(Parent|((Eth|Fc)Network|(L|S)anConnectivity|Ldap|Port|Storage)Policy|SwitchClusterProfile(Template))')
    if any(re.search(preg, i) for i in ikeys):
        parent_match = next((i for i in ikeys if re.search(preg, i)), None)
        psplit = kwargs.intersight_object_map[iresults.ObjectType].split('.')
        if len(psplit) > 2:
            policy_name = psplit[1]
        else:
            policy_name = psplit[-1]
        ptitle = mod_pol_description(
            (' '.join(policy_name.split('_'))).title())
        if 'vnic.EthIf' == iresults.ObjectType:
            name = f"vNIC {iresults.Name}"
        elif 'vnic.FcIf' == iresults.ObjectType:
            name = f"vHBA {iresults.Name}"
        elif 'PcId' in ikeys:
            name = f"{ptitle} - PortChannel `{iresults.PcId}`"
        elif 'PortId' in ikeys:
            name = f"{ptitle} - Port `{iresults.PortId}`"
        elif 'PortIdStart' in ikeys:
            name = f"{ptitle} - PortIdStart `{iresults.PortIdStart}`"
        elif 'Server' in ikeys:
            name = f"{ptitle} - `{iresults.Server}`"
        elif 'ManualDriveGroup' in ikeys:
            name = f"{ptitle} - DriveGroup `{iresults.Name}`"
        elif 'VlanId' in ikeys:
            name = f"{ptitle} - VLAN `{iresults.VlanId}`"
        elif 'VsanId' in ikeys:
            name = f"{ptitle} - VSAN `{iresults.VsanId}`"
        else:
            name = f"{ptitle} - `{iresults.Name}`"
        rsplit = kwargs.intersight_object_map[iresults.ObjectType].split('.')
        parent_policy = rsplit[0]
        parent_cache_entry = kwargs.intersight_api[kwargs.org][category][parent_policy][iresults[parent_match].Moid]
        # Extract the name from the DotMap cache entry
        parent_name = parent_cache_entry.name if hasattr(parent_cache_entry, 'name') else parent_cache_entry
        parent_title = mod_pol_description(
            (parent_policy.replace('_', ' ')).title())
        rtype = DESCRIPTION_WORD_MAP.get(
            category.replace(
                '_', ' ').title(), category.replace(
                '_', ' ').title())
        if method == 'post':
            pcolor.Green(
                f'{" " * 6}* Completed {method.upper()} for Organization: `{kwargs.org}` > {parent_title} {rtype} `{parent_name}`: {name} - Moid: {pmoid}')
        else:
            pcolor.LightPurple(
                f'{" " * 6}* Completed {method.upper()} for Organization: `{kwargs.org}` > {parent_title} {rtype} `{parent_name}`: {name} - Moid: {pmoid}')
        return
    if re.search(regex, iresults.ObjectType):
        if 'SharingRule' in iresults.ObjectType:
            resource = 'iam_sharing_rule'
        else:
            resource = kwargs.intersight_object_map[iresults.ObjectType]
        ptype = mod_pol_description(resource.replace('_', ' ').title())
        if 'Key' in ikeys:
            name = f"{ptype}: `{iresults.Key}`"
        else:
            name = f"{ptype}: `{iresults.Name}`"
        if method == 'post':
            pcolor.Green(
                f'{" " * 6}* Completed {method.upper()} for System -> {name} - Moid: {pmoid}')
        else:
            pcolor.LightPurple(
                f'{" " * 6}* Completed {method.upper()} for System -> {name} - Moid: {pmoid}')
        return
    if 'asset.DeviceClaim' == iresults.ObjectType:
        name = f"Claiming Server `{iresults.SerialNumber}` Registration"
    elif 'autosupport' == ptype:
        name = "AutoSupport"
    elif 'user_role' in ptype:
        name = f"Role for {ptype}"
    elif 'upgrade' in ptype:
        name = f".  Performing Firmware Upgrade on {kwargs.serial} - {kwargs.server} Server Profile"
    elif 'UserId' in ikeys:
        name = f"{iresults.UserId} CCO User Authentication"
    elif 'eula' in ptype:
        name = "Account EULA Acceptance"
    elif 'Action' in ikeys:
        if iresults.Action == 'Deploy':
            name = f"Deploy Profile {pmoid}"
        else:
            name = iresults['Name']
    elif 'ScheduledActions' in ikeys:
        name = f"Activating Profile {pmoid}"
    elif 'Targets' in ikeys:
        name = iresults['Targets'][0]['Name']
    elif 'update_tags' in ptype:
        name = f"Tags updated for Physical Server attached to {kwargs.tag_server_profile}"
    elif 'Identity' in ikeys:
        name = f"Reservation: `{iresults.Identity}`"
    elif 'Name' in ikeys:
        name = iresults['Name']
    elif 'EndPointRole' in ikeys:
        users = DotMap()
        for k, v in kwargs.user_moids.items():
            users[v.moid] = k
        name = list(
            users.values())[
            list(
                users.keys()).index(
                iresults.EndPointUser.Moid)]
    if name is None:
        print(json.dumps(iresults, indent=4))
        print(kwargs.ptype)
        print(kwargs.parent_name)
        print(kwargs.parent_type)
        print('missing definition')
        sys.exit(1)
    if re.search('^(Activating|Deploy)', name):
        pcolor.Cyan(f'      * {name}.')
    if re.search('(eula|upgrade)', ptype) and ptype == 'firmware':
        if method == 'post':
            pcolor.Green(
                f'{" " * 6}* Completed {method.upper()} for {ptype} {name}.')
        else:
            pcolor.LightPurple(
                f'      * Completed {method.upper()} for {ptype} {name}.')
    elif 'Claiming' in name:
        pcolor.Green(f'{" " * 6}- Completed POST for {name} - Moid: {pmoid}')
    elif 'Reservation' in name:
        pcolor.Green(f'{" " * 6}- Completed POST for {name} - Moid: {pmoid}')
    elif 'bulk/MoMergers' == kwargs.uri:
        if method == 'post':
            pcolor.Green(
                f'{" " * 6}- Completed Bulk Merger {method.upper()} for Organization: `{kwargs.org}` > Name: {name} - Moid: {pmoid}')
        else:
            pcolor.LightPurple(
                f'{" " * 4}- Completed Bulk Merger {method.upper()} for Organization: `{kwargs.org}` > Name: {name} - Moid: {pmoid}')
    else:
        rtype = mod_pol_description(ptype.replace('_', ' ').title())
        if method == 'post':
            pcolor.Green(
                f'{" " * 6}- Completed {method.upper()} for Organization: `{kwargs.org}` Name: {name} - Moid: {pmoid}')
        else:
            pcolor.LightPurple(
                f'{" " * 6}- Completed {method.upper()} for Organization: `{kwargs.org}` > Name: {name} - Moid: {pmoid}')


def deploy_notification(profile, profile_type):
    """Print a deploy-in-progress notification for a profile."""
    pcolor.LightGray(f'\n{"-" * 108}\n')
    pcolor.LightPurple(
        f'   Deploy Action Still ongoing for {profile_type} Profile {profile}')
    pcolor.LightGray(f'\n{"-" * 108}\n')


def end_loop(ptype1, ptype2):
    """Print a section-end banner after a deployment loop."""
    pcolor.LightPurple(
        f"\n   Completed {' '.join(ptype1.split('_')).title()} {ptype2} Deployment.")


def section_begin(resource_type, resource):
    """Print a section-begin header for an Intersight resource deployment."""
    ptype1 = ' '.join(resource_type.split('_')).title()
    ptype2 = mod_pol_description((' '.join(resource.split('_'))).title())
    pcolor.LightGray(f'\n{"-" * 108}\n')
    pcolor.LightPurple(
        f"  Beginning Intersight -> {ptype1} -> {ptype2} Deployments.\n")


def section_end(resource_type, resource):
    """Print a section-end header for an Intersight resource deployment."""
    ptype1 = ' '.join(resource_type.split('_')).title()
    ptype2 = mod_pol_description((' '.join(resource.split('_'))).title())
    pcolor.LightGray(f'\n{"-" * 108}\n')
    pcolor.LightPurple(
        f"  Completed Intersight -> {ptype1} -> {ptype2} Deployments.\n")


def section_begin_c88x(resource_type, resource):
    """Print a section-begin header for a C88x resource deployment."""
    ptype1 = ' '.join(resource_type.split('_')).title()
    ptype2 = mod_pol_description((' '.join(resource.split('_'))).title())
    pcolor.LightGray(f'\n{"-" * 108}\n')
    pcolor.LightPurple(f"  Beginning {ptype1} -> {ptype2} Deployment.\n")


def section_end_c88x(resource_type, resource):
    """Print a section-end header for a C88x resource deployment."""
    ptype1 = ' '.join(resource_type.split('_')).title()
    ptype2 = mod_pol_description((' '.join(resource.split('_'))).title())
    pcolor.LightGray(f'\n{"-" * 108}\n')
    pcolor.LightPurple(f"  Completed {ptype1} -> {ptype2} Deployment.\n")


def section_begin_org(org, resource, resource_type):
    """Print a section-begin header scoped to a specific organization."""
    ptype1 = ' '.join(resource_type.split('_')).title()
    ptype2 = mod_pol_description((' '.join(resource.split('_'))).title())
    pcolor.LightGray(f'\n{"-" * 108}\n')
    pcolor.LightPurple(
        f"  Beginning Intersight -> {ptype1} -> {ptype2} Deployments for Organization: `{org}`.\n")


def section_end_org(org, resource, resource_type):
    """Print a section-end header scoped to a specific organization."""
    ptype1 = ' '.join(resource_type.split('_')).title()
    ptype2 = mod_pol_description((' '.join(resource.split('_'))).title())
    pcolor.LightPurple(
        f"\n  Completed Intersight -> {ptype1} -> {ptype2} Deployments for Organization: `{org}`.")

# =============================================================================
# Errors
# =============================================================================


def error_file_location(var_name, var_value):  # pylint: disable=invalid-name
    """Print an error for an invalid file location variable and exit."""
    pcolor.LightGray(f'\n{"-" * 108}\n')
    pcolor.Yellow(f'  !!! ERROR !!! The "{var_name}" "{var_value}"')
    pcolor.Yellow(f'  is invalid.  Please valid the Entry for "{var_name}".')
    pcolor.LightGray(f'\n{"-" * 108}\n')
    sys.exit(1)


def error_organization(org):
    """Print an error for a missing Intersight organization and exit."""
    pcolor.LightGray(f'\n{"-" * 108}\n')
    pcolor.Yellow('   !!! ERROR !!!')
    pcolor.Yellow(
        '   The organization was not found in Intersight, but it is referenced in the input file.')
    pcolor.Yellow(f'   Organization: {org}')
    pcolor.LightGray(f'\n{"-" * 108}\n')
    sys.exit(1)


def error_requests(method, status, text, uri):
    """Print an HTTP error response and exit."""
    pcolor.LightGray(f'\n{"-" * 108}\n')
    pcolor.Yellow(f'   !!! ERROR !!! when attempting {method} to {uri}')
    pcolor.Yellow(f'   Exiting on Error {status} with the following output:')
    pcolor.Yellow(f'   {text}')
    pcolor.LightGray(f'\n{"-" * 108}\n')
    sys.exit(1)


# =============================================================================
# Messages
# =============================================================================
def message_invalid_selection():
    """Print an error for an invalid menu selection."""
    pcolor.Red(
        f'\n{"-" * 108}\n\n  !!!Error!!! Invalid Selection.  Please Select a valid Option from the List.')
    pcolor.Red(f'\n{"-" * 108}\n')


def message_invalid_y_or_n(length):
    """Print an error for a Y/N prompt receiving an invalid response."""
    if length == 'short':
        dash_rep = '-' * 54
    else:
        dash_rep = '-' * 108
    pcolor.Red(
        f'\n{dash_rep}\n\n  !!!Error!!! Invalid Value.  Please enter `Y` or `N`.')
    pcolor.Red(f'\n{dash_rep}\n')


def message_fcoe_vlan(fcoe_id, vlan_policy):
    """Print an error when a FCoE VLAN ID conflicts with the VLAN policy."""
    pcolor.Red(
        f'\n{"-" * 108}\n\n  !!!Error!!!\n  The FCoE VLAN `{fcoe_id}` is already assigned to the VLAN Policy')
    pcolor.Red(
        f'  {vlan_policy}.  Please choose a VLAN id that is not already in use.')
    pcolor.Red(f'\n{"-" * 108}\n')


def message_invalid_native_vlan(native_vlan, vlan_list):  # pylint: disable=invalid-name
    """Print an error when the native VLAN is not in the VLAN policy list."""
    pcolor.Red(
        f'\n{"-" * 108}\n\n  !!!Error!!!\n  The Native VLAN `{native_vlan}` was not in the VLAN Policy List.')
    pcolor.Red(f'  VLAN Policy List is: "{vlan_list}"')
    pcolor.Red(f'\n{"-" * 108}\n')


def message_invalid_vxan():
    """Print an error for an invalid VXAN/VLAN ID entry."""
    pcolor.Red(
        f'\n{"-" * 108}\n\n  !!!Error!!!\n  Invalid Entry.  Please Enter a valid ID in the range of 1-4094.')
    pcolor.Red(f'\n{"-" * 108}\n')


def message_invalid_vsan_id(vsan_policy, vsan_id, vsan_list):
    """Print an error when a VSAN ID is not in the VSAN policy."""
    pcolor.Red(
        f'\n{"-" * 108}\n\n  !!!Error!!!\n  The VSAN `{vsan_id}` is not in the VSAN Policy `{vsan_policy}`.')
    pcolor.Red(f'  Options are: {vsan_list}.\n\n{"-" * 108}\n')


def message_starting_over(policy_type):
    """Print a notice that a policy section is restarting from the beginning."""
    pcolor.Yellow(f'\n{"-" * 54}\n\n  Starting `{policy_type}` Section over.')
    pcolor.Yellow(f'\n{"-" * 54}\n')
