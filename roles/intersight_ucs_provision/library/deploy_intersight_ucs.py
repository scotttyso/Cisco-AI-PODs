"""Deploy Intersight UCS -
Use This to Deploy Intersight UCS configurations or for C88XA-M8 deploy to the server directly.
It uses argparse to take in the following CLI arguments:
        Base arguments:
            -d   or --dir:                   Base directory used for YAML configuration files.
            -c   or --check:               Run in check mode.  The Model definitions will only be compared to the Intersight API.
            -dl  or --debug-level:           Debug output level.
            -i   or --ignore-tls:            Ignore TLS server-side certificate verification.
            -ni  or --non-interactive:       Run in non-interactive mode with defaults.
            -ie  or --intersight-environment: Target Intersight environment (saas, cva, pva).
"""
# =============================================================================
# Source Modules
# =============================================================================
import sys
from pathlib import Path


def prRed(message: str) -> None:
    """Print a red terminal message."""
    print("\033[91m {}\033[00m".format(message))


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
    import argparse
    import os
    from dotmap import DotMap
    from typing import Any
    from roles.intersight_ucs_provision.library.src import initialize, pcolor, shared_functions
except ImportError as error:
    prRed(f'Deploy UCS - !!! ERROR !!!\n{error.__class__.__name__}')
    prRed(f" Module {error.name} is required to run this script")
    prRed(
        f" Install the module using the following: `pip install {error.name}`")
    raise SystemExit(1) from error

# =============================================================================
# Function - Base Arguments
# =============================================================================


def base_arguments(parser):
    parser.add_argument(
        '-a',
        '--intersight-api-key-id',
        default=os.getenv('intersight_api_key_id'),
        help='The Intersight API key id for HTTP signature scheme.')
    parser.add_argument(
        '-d',
        '--dir',
        default='user_environment',
        help='The Directory where the YAML configuration files are located.')
    parser.add_argument(
        '-dl', '--debug-level', default=0,
        help='Used for troubleshooting.  The Amount of Debug output to Show: '
        '1. Shows the api request response status code '
        '5. Show URL String + Lower Options '
        '6. Adds Results + Lower Options '
        '7. Adds json payload + Lower Options '
        'Note: payload shows as pretty and straight to check for stray object types like Dotmap and numpy')
    parser.add_argument(
        '-f',
        '--intersight-fqdn',
        default='intersight.com',
        help='The Directory to use for the Creation of the YAML Configuration Files.')
    parser.add_argument(
        '-i',
        '--ignore-tls',
        action='store_false',
        help='Ignore TLS server-side certificate verification.  Default is False.')
    parser.add_argument(
        '-ie',
        '--intersight-environment',
        default=os.getenv('INTERSIGHT_ENVIRONMENT'),
        choices=['saas', 'cva', 'pva'],
        help='Target Intersight environment: saas (default), cva, or pva.')
    parser.add_argument(
        '-k',
        '--intersight-secret-key',
        default=os.getenv('intersight_secret_key'),
        help='Name of the file containing The Intersight secret key or contents of the secret key in environment.')
    parser.add_argument(
        '-ni',
        '--non-interactive',
        action='store_true',
        help='Run in non-interactive mode with default values (no prompts).')
    parser.add_argument(
        '-y',
        '--yaml-file',
        default=None,
        help='The input YAML File.')
    return parser

# =============================================================================
# Function: Parse Arguments
# =============================================================================


def cli_arguments() -> Any:
    """Parse CLI arguments for Deploy Intersight UCS and return them as a DotMap for kwargs."""
    parser = argparse.ArgumentParser(
        description='Deploy Intersight UCS Module')
    parser = base_arguments(parser)
    parser.add_argument(
        '-c',
        '--check',
        action='store_true',
        help='Boolean flag to enable check mode')
    return DotMap(args=parser.parse_args())

# =============================================================================
# Function: Main Script
# =============================================================================


def main() -> int:
    """Program entrypoint for Deploy Intersight UCS CLI."""
    # =========================================================================
    # Configure Base Module Setup
    # =========================================================================
    pcolor.Cyan(
        f'\n{"-" * 108}\n\n  Starting -> Deploy Intersight/UCS CLI!\n\n{"-" * 108}\n')
    kwargs = cli_arguments()
    
    # =========================================================================
    # Feature 2: Initialize multi-environment support
    # =========================================================================
    try:
        from src.intersight.intersight_environment import (
            MultiEnvironmentVault, EnvironmentDetector, SchemaCache
        )
        
        # Initialize vault and environment detector
        vault = MultiEnvironmentVault()
        detector = EnvironmentDetector(vault)
        
        # Detect target environment (priority: CLI arg > env var > endpoint pattern > default)
        intersight_env = detector.get_target_environment(
            env_var=kwargs.args.intersight_environment,
            endpoint=kwargs.args.intersight_fqdn
        )
        
        # Store environment in kwargs for later use
        kwargs.intersight_environment = intersight_env
        
        # Validate credentials exist for target environment. Without the legacy per-user vault the credentials
        # come from the environment (deploy_ai_pod.py exports them from the selected environment's vault).
        try:
            if vault.vault_path.exists():
                detector.validate_credentials(intersight_env)
            elif not (kwargs.args.intersight_api_key_id and kwargs.args.intersight_secret_key):
                raise ValueError(
                    'No Intersight credentials: set intersight_api_key_id and intersight_secret_key '
                    f'(or create {vault.vault_path})')
            pcolor.Cyan(f'  ✅ Using {intersight_env.upper()} environment')
        except ValueError as e:
            pcolor.Red(f'  ❌ {e}')
            return 1
        
        # Initialize schema cache for filtering
        kwargs.schema_cache = SchemaCache()
        
    except ImportError:
        # Feature 2 modules not available, default to SaaS
        kwargs.intersight_environment = 'saas'
        pcolor.Yellow('  ⚠️  Feature 2 modules not found, defaulting to SaaS')
    except Exception as e:
        pcolor.Red(f'  ❌ Error during environment initialization: {e}')
        return 1
    
    kwargs = shared_functions.base_script_settings(kwargs)
    kwargs = shared_functions.load_configurations(kwargs)
    kwargs = shared_functions.intersight_config(kwargs)
    kwargs = initialize.begin('intersight',
                              'deployment').functions_to_run(kwargs)
    pcolor.Cyan(
        f'\n{"-" * 108}\n\n  !!! Procedures Complete !!!\n  Closing Environment and Exiting Script...\n\n{"-" * 108}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
