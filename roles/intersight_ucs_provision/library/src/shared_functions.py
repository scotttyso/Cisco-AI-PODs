"""Shared utility functions for Intersight UCS provisioning."""
# pylint: disable=invalid-name,missing-class-docstring,missing-function-docstring,too-many-branches,too-many-statements,too-many-locals,too-many-ancestors
# =============================================================================
# Source Modules
# =============================================================================
import sys
from pathlib import Path


def prRed(skk):
    print(f"\033[91m {skk}\033[00m")


SCRIPT_PATH = Path(__file__).resolve().parent
CLASSES_PATH = SCRIPT_PATH / 'src'
REPO_ROOT = SCRIPT_PATH.parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPT_PATH) not in sys.path:
    sys.path.insert(1, str(SCRIPT_PATH))
if str(CLASSES_PATH) not in sys.path:
    sys.path.insert(2, str(CLASSES_PATH))

try:
    from roles.intersight_ucs_provision.library.src import notifications, pcolor, validating
    from copy import deepcopy
    from dotmap import DotMap
    from json_ref_dict import materialize, RefDict
    from OpenSSL import crypto
    import importlib
    import importlib.util
    import itertools
    import json
    import logging
    import os
    import platform
    import re
    import yaml
except ImportError as e:
    prRed(f'src/shared_functions.py - !!! ERROR !!!\n{e.__class__.__name__}')
    prRed(f' Module {e.name} is required to run this script')
    prRed(f' Install the module using the following: `pip install {e.name}`')
    sys.exit(1)
# =============================================================================
# Log levels 0 = None, 1 = Class only, 2 = Line
# =============================================================================
log_level = 2
# =============================================================================
# Exception Classes and YAML dumper
# =============================================================================


class insufficient_args(Exception):
    pass


class yaml_dumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)

# =============================================================================
# Function - Basic Setup for the Majority of the modules
# =============================================================================


def base_script_settings(kwargs):
    # =========================================================================
    # Configure logger and Build kwargs
    # =========================================================================
    script_name = (sys.argv[0].split(os.sep)[-1]).split('.')[0]
    dest_dir = f'{Path.home()}{os.sep}Logs'
    dest_file = script_name + '.log'
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    Path(os.path.join(dest_dir, dest_file)).touch(exist_ok=True)
    FORMAT = '%(asctime)-15s [%(levelname)s] [%(filename)s:%(lineno)s] %(message)s'
    logging.basicConfig(
        filename=f'{dest_dir}{os.sep}{script_name}.log',
        filemode='a',
        format=FORMAT,
        level=logging.DEBUG)
    logger = logging.getLogger('openapi')
    # =========================================================================
    # Mirror all print()/pcolor output to the log file
    # =========================================================================
    pcolor.init_log(os.path.join(dest_dir, dest_file))
    # =========================================================================
    # Determine the Script Path
    # =========================================================================
    args_dict = vars(kwargs.args)
    for k, v in args_dict.items():
        if isinstance(v, str) and v is not None:
            os.environ[k] = v
    kwargs.script_name = (sys.argv[0].split(os.sep)[-1]).split('.')[0]
    kwargs.script_path = os.path.dirname(os.path.realpath(sys.argv[0]))
    kwargs.schema_path = str(REPO_ROOT / 'schema')
    kwargs.args.dir = os.path.abspath(kwargs.args.dir)
    kwargs.home = Path.home()
    kwargs.logger = logger
    kwargs.op_system = platform.system()
    kwargs.imm_dict.orgs = DotMap()
    kwargs.type_dotmap = type(DotMap())
    kwargs.type_none = type(None)
    # =========================================================================
    # Import Stored Parameters and Add to kwargs
    # =========================================================================
    with open(os.path.join(kwargs.schema_path, 'cisco-ai-pods.json'), encoding='utf8') as f:
        ezdata = json.load(f)
    ezdata.pop('$ref')
    with open(os.path.join(kwargs.schema_path, 'temp.json'), 'w', encoding='utf-8') as f:
        json.dump(ezdata, f, indent=4)
    ezdata = materialize(
        RefDict(
            os.path.join(
                kwargs.schema_path,
                'temp.json'),
            'r',
            encoding='utf8'))
    if os.path.exists(os.path.join(kwargs.schema_path, 'temp.json')):
        os.remove(os.path.join(kwargs.schema_path, 'temp.json'))
    script_tag = script_name.replace('ez', 'easy-')
    kwargs.ez_tags = [{'key': 'Provisioned via -', 'value': script_tag},
                      {'key': f'{script_tag} version -', 'value': ezdata['x-schema-version']}]
    kwargs.ezdata = DotMap(ezdata['definitions'])
    kwargs.intersight_object_map = DotMap()
    for k, v in kwargs.ezdata.items():
        vkeys = list(v.keys())
        if 'intersight.' in k and 'x-intersight-object-type' in vkeys:
            if re.search(
                '^intersight\\.(policies|pools|profiles|system|templates)\\.',
                    k):
                ptype = re.search('^intersight\\.([a-z_]+)\\.', k).group(1)
                object_type = v['x-intersight-object-type']
                if not kwargs.intersight_object_map.get(object_type):
                    kwargs.intersight_object_map[object_type] = k.replace(
                        f'intersight.{ptype}.', '')
                    kwargs.intersight_object_map[k.replace(
                        f'intersight.{ptype}.', '')] = object_type
    kwargs.intersight_object_map = DotMap(
        sorted(kwargs.intersight_object_map.toDict().items()))
    # =========================================================================
    # Get Intersight Configuration
    # - apikey
    # - endpoint
    # - keyfile
    # =========================================================================
    if kwargs.args.intersight_secret_key:
        if '~' in kwargs.args.intersight_secret_key:
            kwargs.args.intersight_secret_key = os.path.expanduser(
                kwargs.args.intersight_secret_key)
    if os.getenv('intersight_fqdn'):
        kwargs.args.intersight_fqdn = os.getenv('intersight_fqdn')
    if kwargs.args.intersight_fqdn and 'api/v1/iam/Users' in kwargs.args.intersight_fqdn:
        kwargs.args.intersight_fqdn = (
            (kwargs.args.intersight_fqdn).replace(
                'https://', '')).split('/')[0]
    elif os.getenv('intersight_fqdn'):
        kwargs.args.intersight_fqdn = os.getenv('intersight_fqdn')
    # =========================================================================
    # Check Folder Structure for Illegal Characters
    # =========================================================================
    for folder in kwargs.args.dir.split(os.sep):
        if folder == '':
            pass
        elif not re.search(r'^[\w\@\-\.\:\/\\]+$', folder):
            pcolor.Red(f'\n{"-" * 108}\n\n  !!ERROR!!')
            pcolor.Red(
                '  The Directory structure can only contain the following characters:')
            pcolor.Red(
                '  letters(a-z, A-Z), numbers(0-9), hyphen(-), period(.), colon(:), and underscore(-).')
            pcolor.Red(
                f'  It can be a short path or a fully qualified path.  `{folder}` does not qualify.')
            pcolor.Red(f'  Exiting...\n\n{"-" * 108}\n')
            raise ValueError(f'Invalid directory component: {folder}')
    return kwargs

# =========================================================================
# Function - Lookup Certificate and Private Key Files, Check for Validity, and Return Contents
# =========================================================================


def cert_file_check(expected_type, file_path):
    # Expand ~ to home directory
    file_path = os.path.expanduser(file_path)
    if not isinstance(file_path, str) or len(file_path.strip()) == 0:
        pcolor.Red(
            f'!!! ERROR !!! `{expected_type}` file path is empty for Intersight Secret Key.')
        sys.exit(1)
    if not os.path.isfile(file_path):
        pcolor.Red(
            f'!!! ERROR !!! `{expected_type}` file `{file_path}` was not found for Intersight Secret Key.')
        sys.exit(1)
    try:
        with open(file_path, 'r', encoding='utf-8') as cert_file:
            cert_content = cert_file.read()
    except OSError as exc:
        pcolor.Red(
            f'!!! ERROR !!! Failed to read `{expected_type}` file `{file_path}` for Intersight Secret Key: {exc}')
        sys.exit(1)

    if 'PRIVATE KEY' in cert_content:
        try:
            crypto.load_privatekey(crypto.FILETYPE_PEM, cert_content)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            pcolor.Red(
                f'!!! ERROR !!! `{file_path}` is not a valid PEM private key: {exc}')
            sys.exit(1)
        detected_type = 'private_key'
    else:
        pcolor.Red(
            f'!!! ERROR !!! `{file_path}` is not a valid private key file.')
        sys.exit(1)
    if detected_type != expected_type:
        pcolor.Red(
            f'!!! ERROR !!! `{file_path}` contains a `{detected_type}` but `{expected_type}` was expected.')
        sys.exit(1)


# =============================================================================
# Function - Prompt User for the Intersight Configurtion
# =============================================================================
def intersight_config(kwargs):
    # =========================================================================
    # Prompt User for Intersight API Key
    # =========================================================================
    if '~' in kwargs.args.intersight_secret_key:
        kwargs.args.intersight_secret_key = os.path.expanduser(
            kwargs.args.intersight_secret_key)
    cert_file_check(expected_type='private_key',
                    file_path=kwargs.args.intersight_secret_key)
    # =========================================================================
    # Prompt User for Intersight FQDN
    # =========================================================================
    non_interactive = bool(getattr(kwargs.args, 'non_interactive', False))
    loaded_fqdn = kwargs.get(
        'intersight',
        DotMap()).get(
        'script_settings',
        DotMap()).get('intersight_fqdn')
    if (not kwargs.args.intersight_fqdn) and loaded_fqdn:
        kwargs.args.intersight_fqdn = loaded_fqdn
    if kwargs.args.intersight_fqdn and 'api/v1/iam/Users' in kwargs.args.intersight_fqdn:
        kwargs.args.intersight_fqdn = (
            (kwargs.args.intersight_fqdn).replace(
                'https://', '')).split('/')[0]

    valid = False
    while not valid:
        varValue = kwargs.args.intersight_fqdn
        valid = False
        if varValue is not None:
            varName = 'Intersight FQDN'
            if re.search(r'^[a-zA-Z0-9]{1,4}:', varValue):
                valid = validating.ip_address(varName, varValue)
            elif re.search(r'[a-zA-Z]', varValue):
                valid = validating.dns_name(varName, varValue)
            elif re.search(r'^([0-9]{1,3}\.){3}[0-9]{1,3}$', varValue):
                valid = validating.ip_address(varName, varValue)
            else:
                pcolor.Red(
                    f'\n{"-" * 108}\n\n  "{varValue}" is not a valid address.\n\n{"-" * 108}\n')
        if not valid:
            if non_interactive:
                pcolor.Red(
                    '!!! ERROR !!! Non-interactive mode requires a valid Intersight FQDN/IP via CLI/env or loaded variables.')
                pcolor.Red(
                    '  Expected: --intersight-fqdn or env `intersight_fqdn` or `intersight.script_settings.intersight_fqdn` in loaded config.')
                sys.exit(1)
            kwargs.jdata = kwargs.ezdata['abstract.hostname_ip_or_ipv6']
            kwargs.jdata.update(
                DotMap(
                    description='Hostname of the Intersight Fully Qualified Domain Name (FQDN) or IP Address.',
                    default=kwargs.args.intersight_fqdn or 'intersight.com',
                    title='Intersight FQDN/IP'))
            kwargs.args.intersight_fqdn = variable_prompt(kwargs)
    kwargs.args.url = f'https://{kwargs.args.intersight_fqdn}'
    # Return kwargs
    return kwargs

# =============================================================================
# Function - Load Previous YAML Files
# =============================================================================


def load_configurations(kwargs):
    def normalize_value(value):
        if isinstance(value, dict):
            return DotMap({key: normalize_value(item)
                          for key, item in value.items()})
        if isinstance(value, list):
            return [normalize_value(item) for item in value]
        return deepcopy(value)

    def deep_merge_dicts(dest, src):
        for key, value in src.items():
            if key in dest and isinstance(
                    dest[key],
                    dict) and isinstance(
                    value,
                    dict):
                deep_merge_dicts(dest[key], value)
            elif key in dest and isinstance(dest[key], list) and isinstance(value, list):
                dest[key].extend(normalize_value(value))
            else:
                dest[key] = normalize_value(value)
        return dest

    def collect_ezai_files(root_dir):
        file_list = []
        for walk_entry in os.walk(root_dir):
            current_root = walk_entry[0]
            files = walk_entry[2]
            for file_name in files:
                if file_name.endswith('ezai.yaml'):
                    file_list.append(os.path.join(current_root, file_name))
        return sorted(file_list)

    load_dir = kwargs.args.dir
    if not os.path.isdir(load_dir):
        return kwargs

    for key in ['intersight', 'openshift', 'everpure', 'shared_services']:
        if not kwargs.get(key):
            kwargs[key] = DotMap()

    ezai_files = collect_ezai_files(load_dir)
    for file_path in ezai_files:
        with open(file_path, 'r', encoding='utf-8') as yfile:
            data = yaml.safe_load(yfile)
        if not data or not isinstance(data, dict):
            continue
        for top_key in [
            'intersight',
            'openshift',
            'everpure',
                'shared_services']:
            if data.get(top_key) and isinstance(data[top_key], dict):
                deep_merge_dicts(kwargs[top_key], data[top_key])

    # Backward compatibility for existing workflows that consume
    # kwargs.imm_dict.orgs.
    if kwargs.intersight.get('config') and isinstance(
            kwargs.intersight.config, dict):
        if not kwargs.imm_dict.get('orgs'):
            kwargs.imm_dict.orgs = DotMap()
        deep_merge_dicts(kwargs.imm_dict.orgs, kwargs.intersight.config)
    if kwargs.intersight.get('configure') and isinstance(
            kwargs.intersight.configure, dict):
        if not kwargs.imm_dict.get('orgs'):
            kwargs.imm_dict.orgs = DotMap()
        deep_merge_dicts(kwargs.imm_dict.orgs, kwargs.intersight.configure)
    if kwargs.intersight.get('system') and isinstance(
            kwargs.intersight.system, dict):
        if not kwargs.imm_dict.get('system'):
            kwargs.imm_dict.system = DotMap()
        deep_merge_dicts(kwargs.imm_dict.system, kwargs.intersight.system)
    # Validate required sensitive environment variables referenced by the
    # loaded model.
    try:
        validator_path = os.path.join(
            kwargs.script_path,
            'src',
            'validate_sensitive_variables.py')
        module_name = 'validate_sensitive_variables'
        spec = importlib.util.spec_from_file_location(
            module_name, validator_path)
        if spec is None or spec.loader is None:
            raise ImportError(
                f'Unable to load module spec from {validator_path}')
        validator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(validator)
        model = {
            'intersight': kwargs.intersight.toDict() if hasattr(
                kwargs.intersight,
                'toDict') else kwargs.intersight,
            'openshift': kwargs.openshift.toDict() if hasattr(
                kwargs.openshift,
                'toDict') else kwargs.openshift,
            'everpure': kwargs.everpure.toDict() if hasattr(
                kwargs.everpure,
                'toDict') else kwargs.everpure,
        }
        schema_path = Path(
            os.path.join(
                kwargs.schema_path,
                'cisco-ai-pods.json'))
        success, missing_vars, error_messages, sensitive_vars = validator.validate_all_sensitive_variables(
            model, schema_path)
        if not success:
            pcolor.Red(
                f'\n!!! ERROR !!! Missing {len(missing_vars)} sensitive environment variable(s).')
            for message in error_messages:
                # Preserve per-line formatting/colors from validator output.
                print(message, file=sys.stderr)
            sys.exit(1)
        else:
            kwargs.sensitive_vars = DotMap(sensitive_vars)
    except Exception as error:  # pylint: disable=broad-exception-caught
        pcolor.Red(
            f'\n!!! ERROR !!! validate_sensitive_variables failed during load_configurations: {error}')
        pcolor.Red('shared_functions.py line 893')
        raise

    # Return kwargs
    return kwargs

# =============================================================================
# Function - Prompt for Answer to Question from List
# =============================================================================


def variable_from_list(kwargs):
    # =========================================================================
    # Set Function Variables
    # =========================================================================
    default = kwargs.jdata.default
    description = kwargs.jdata.description
    optional = False  # pylint: disable=unused-variable
    title = kwargs.jdata.title
    if not kwargs.jdata.get('multi_select'):
        kwargs.jdata.multi_select = False
    # =========================================================================
    # Sort the Variables
    # =========================================================================
    if not kwargs.jdata.get('sort'):
        vars = kwargs.jdata.enum  # pylint: disable=redefined-builtin
    else:
        vars = sorted(kwargs.jdata.enum, key=str.casefold)  # pylint: disable=redefined-builtin
    valid = False
    while not valid:
        pcolor.LightPurple(f'\n{"-" * 108}\n')
        if '\n' in description:
            description = description.split('\n')
            for line in description:
                pcolor.LightGray(line)
        else:
            pcolor.LightGray(description)
        if kwargs.jdata.get('multi_select'):
            pcolor.Yellow(
                '\n     Note: Answer can be:\n       * Single: 1\n       * Multiple: `1,2,3` or `1-3,5-6`')
        if kwargs.jdata.get('multi_select'):
            pcolor.Yellow('    Select Option(s) Below:')
        else:
            pcolor.Yellow('\n    Select an Option Below:')
        default_index = 0
        for index, value in enumerate(vars):
            index += 1
            if value == default:
                default_index = index
            if index < 10:
                pcolor.Cyan(f'      {index}. {value}')
            elif index < 100:
                pcolor.Cyan(f'     {index}. {value}')
            elif index > 99:
                pcolor.Cyan(f'    {index}. {value}')
        if kwargs.jdata.get('multi_select'):
            if kwargs.jdata.get('optional'):
                optional = True
                var_selection = input(
                    f'\nPlease Enter the Option Number(s) to select for {title}.  [press enter to skip]: ')
            elif not default == '':
                var_selection = input(
                    f'\nPlease Enter the Option Number(s) to select for {title}.  [{default_index}]: ')
            else:
                var_selection = input(
                    f'\nPlease Enter the Option Number(s) to select for {title}: ')
        else:
            if kwargs.jdata.get('optional'):
                optional = True
                var_selection = input(
                    f'\nPlease Enter the Option Number to select for {title}.  [press enter to skip]: ')
            elif not default == '':
                var_selection = input(
                    f'\nPlease Enter the Option Number to select for {title}.  [{default_index}]: ')
            else:
                var_selection = input(
                    f'\nPlease Enter the Option Number to select for {title}: ')
        if kwargs.jdata.get('optional') and var_selection == '' and not kwargs.jdata.multi_select:
            return '', True
        if kwargs.jdata.get('optional') and var_selection == '' and kwargs.jdata.multi_select:
            return [], True
        if default != '' and var_selection == '':
            var_selection = default_index
        if not kwargs.jdata.multi_select and re.search(
                r'^[0-9]+$', str(var_selection)):
            for index, value in enumerate(vars):
                index += 1
                if int(var_selection) == index:
                    selection = value
                    valid = True
        elif kwargs.jdata.multi_select and re.search(r'(^[0-9]+$|^[0-9\-,]+[0-9]$)', str(var_selection)):
            if kwargs.jdata.keep_order:
                var_list = var_selection.split(',')
                kwargs.selection_list = var_list
            else:
                var_list = vlan_list_full(var_selection)
            var_length = int(len(var_list))
            var_count = 0
            selection = []
            for index, value in enumerate(vars):
                index += 1
                for vars in var_list:
                    if int(vars) == index:
                        var_count += 1
                        selection.append(value)
            if var_count == var_length:
                valid = True
            else:
                pcolor.Red(
                    f'\n{"-" * 108}\n\n  The list of Vars {var_list} did not match the available list.\n\n{"-" * 108}\n')
        if not valid:
            notifications.message_invalid_selection()
    return selection, valid

# =============================================================================
# Function - Prompt User for Answer to Question
# =============================================================================


def variable_prompt(kwargs):
    # =========================================================================
    # Improper Value Notifications
    # =========================================================================
    def invalid_boolean(title, answer):
        pcolor.Red(
            f'\n{"-" * 108}\n   `{title}` value of `{answer}` is Invalid!!! Please enter `Y` or `N`.\n{"-" * 108}\n')

    def invalid_integer(title, answer, minimum, maximum):
        pcolor.Red(
            f'\n{"-" * 108}\n   `{title}` value of `{answer}` is Invalid!!!  Valid range is `{minimum}-{maximum}`.\n{"-" * 108}\n')

    def invalid_string(title, answer):
        pcolor.Red(
            f'\n{"-" * 108}\n   `{title}` value of `{answer}` is Invalid!!!\n{"-" * 108}\n')
    # =========================================================================
    # Set Function Variables
    # =========================================================================
    default = kwargs.jdata.default
    description = kwargs.jdata.description
    optional = False
    title = kwargs.jdata.title
    # =========================================================================
    # Print `description` if not enum
    # =========================================================================
    if not kwargs.jdata.get('enum'):
        pcolor.LightPurple(f'\n{"-" * 108}\n')
        pcolor.LightGray(f'{description}\n')
    # =========================================================================
    # Prompt User for Answer
    # =========================================================================
    valid = False
    while not valid:
        if kwargs.jdata.get('enum'):
            answer, valid = variable_from_list(kwargs)
        elif kwargs.jdata.type == 'boolean':
            if default:
                default = 'Y'
            else:
                default = 'N'
            answer = input(
                f'\nEnter `Y` for `True` or `N` for `False` for `{title}`. [{default}]: ')
            if answer == '':
                if default == 'Y':
                    answer = True
                elif default == 'N':
                    answer = False
                valid = True
            elif answer == 'N':
                answer = False
                valid = True
            elif answer == 'Y':
                answer = True
                valid = True
            else:
                invalid_boolean(title, answer)
        elif kwargs.jdata.type == 'integer':
            maximum = kwargs.jdata.maximum
            minimum = kwargs.jdata.minimum
            if kwargs.jdata.get('optional'):
                optional = True
                answer = input(
                    f'Enter the value for {title} [press enter to skip]: ')
            else:
                answer = input(f'Enter the Value for {title}. [{default}]: ')
            if optional and answer == '':
                valid = True
            elif answer == '':
                answer = default
            if not optional:
                if re.fullmatch(r'^[0-9]+$', str(answer)):
                    if kwargs.jdata.title == 'snmp_port':
                        valid = notifications.snmp_port(
                            title, answer, minimum, maximum)
                    else:
                        valid = notifications.number_in_range(
                            title, answer, minimum, maximum)
                else:
                    invalid_integer(title, answer, minimum, maximum)
        elif kwargs.jdata.type == 'string':
            if kwargs.jdata.get('optional'):
                optional = True
                answer = input(
                    f'Enter the value for {title} [press enter to skip]: ')
            elif not default == '':
                answer = input(f'Enter the value for {title} [{default}]: ')
            else:
                answer = input(f'Enter the value for {title}: ')
            if optional and answer == '':
                valid = True
            elif answer == '':
                answer = default
                valid = True
            elif not answer == '':
                maxLength = kwargs.jdata.maxLength
                minLength = kwargs.jdata.minLength
                pattern = kwargs.jdata.pattern
                valid = notifications.length_and_regex(
                    answer, minLength, maxLength, pattern, title)
        else:
            invalid_string(title, answer)
    if kwargs.jdata.get('optional'):
        kwargs.jdata.pop('optional')
    if kwargs.jdata.get('multi_select'):
        kwargs.jdata.pop('multi_select')
    return answer

# =============================================================================
# Function - Collapse VLAN List
# =============================================================================


def vlan_list_format(vlan_list_expanded):
    if not vlan_list_expanded:
        return ''

    try:
        vlan_list = sorted(set(int(v) for v in vlan_list_expanded))
    except (TypeError, ValueError) as exc:
        raise ValueError(f'Invalid VLAN list: {vlan_list_expanded}') from exc

    for vlan_id in vlan_list:
        if vlan_id < 1 or vlan_id > 4094:
            raise ValueError(
                f'VLAN ID `{vlan_id}` is out of valid range (1-4094)')

    vgroups = itertools.groupby(
        vlan_list,
        key=lambda item,
        c=itertools.count(): item -
        next(c))
    tempvlans = [list(group_pair[1]) for group_pair in vgroups]
    vlan_list = [str(x[0]) if len(
        x) == 1 else f'{x[0]}-{x[-1]}' for x in tempvlans]
    return ','.join(vlan_list)

# =============================================================================
# Function - Expand VLAN List
# =============================================================================


def vlan_list_full(vlan_list):
    full_vlan_list = []
    try:
        for token in str(vlan_list).split(','):
            token = token.strip()
            if token == '':
                raise ValueError('Empty VLAN token')
            if '-' in token:
                a_str, b_str = token.split('-', 1)
                a = int(a_str.strip())
                b = int(b_str.strip())
                if a > b:
                    raise ValueError(
                        f'Invalid VLAN range `{token}`: start must be <= end')
                for vlan_id in range(a, b + 1):
                    full_vlan_list.append(vlan_id)
            else:
                full_vlan_list.append(int(token))
    except ValueError as exc:
        raise ValueError(f'Invalid VLAN expression: {vlan_list}') from exc

    for vlan_id in full_vlan_list:
        if vlan_id < 1 or vlan_id > 4094:
            raise ValueError(
                f'VLAN ID `{vlan_id}` is out of valid range (1-4094)')

    # Remove duplicates while preserving insertion order.
    return list(dict.fromkeys(full_vlan_list))
