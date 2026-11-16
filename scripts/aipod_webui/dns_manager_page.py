"""DNS Manager page for Cisco AI PODs - Integrated into aipod_webui pages."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List

import yaml
from nicegui import ui

logger = logging.getLogger(__name__)


# Try to import DNS components
try:
    from dns_updater import (
        DNSRecord, InventoryParser, DNSComparator,
        ActiveDirectoryProvider, DNSUpdater
    )
    from dns_validator import DNSValidator
    DNS_COMPONENTS_AVAILABLE = True
except ImportError:
    DNS_COMPONENTS_AVAILABLE = False


@dataclass(frozen=True)
class DNSManagerHandle:
    """Handle for DNS Manager UI state"""
    last_validation_results: Optional[Dict] = None
    last_update_results: Optional[Dict] = None
    config: Optional[Dict] = None


class DNSManagerPage:
    """DNS Manager page implementation for NiceGUI"""

    def __init__(self, context):
        self.context = context
        self.last_validation_results = None
        self.last_update_results = None
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load DNS configuration"""
        config_paths = [
            Path(__file__).parent / 'dns_config.yaml',
            Path(__file__).parent.parent / 'dns_config.yaml',
        ]
        
        for config_file in config_paths:
            if config_file.exists():
                try:
                    with open(config_file) as f:
                        return yaml.safe_load(f) or {}
                except Exception as e:
                    logger.warning(f"Failed to load config from {config_file}: {e}")
        
        return {}

    def build(self):
        """Build the DNS Manager UI"""
        if not DNS_COMPONENTS_AVAILABLE:
            ui.notify('DNS components not available - ensure dns_updater.py and dns_validator.py are in scripts directory')
            ui.label('⚠️ DNS Manager components not available').classes('text-red-600')
            return

        with ui.row().classes('w-full items-center mb-4'):
            ui.label('🔧 DNS Manager').classes('text-2xl font-bold')
            ui.space()
            ui.label(f'Last updated: {datetime.now().strftime("%H:%M:%S")}').classes('text-xs opacity-50')

        with ui.tabs().classes('w-full') as tabs:
            with ui.tab_panel('Validator'):
                self._build_validator_panel()
            
            with ui.tab_panel('Updater'):
                self._build_updater_panel()
            
            with ui.tab_panel('Status'):
                self._build_status_panel()

    def _build_validator_panel(self):
        """DNS validation for pre-installation checks"""
        with ui.card().classes('w-full'):
            ui.label('📍 Pre-Installation DNS Validation').classes('font-semibold')
            ui.label('Verify DNS records before OpenShift installation').classes('text-sm opacity-75')

            with ui.row().classes('w-full gap-4'):
                # Configuration inputs
                with ui.column().classes('flex-1 gap-2'):
                    ui.label('Cluster Configuration').classes('font-semibold')
                    
                    cluster_name = ui.input(
                        label='Cluster Name',
                        value='prod',
                        placeholder='e.g., prod'
                    ).classes('w-full')
                    
                    domain = ui.input(
                        label='Domain',
                        value='example.com',
                        placeholder='e.g., example.com'
                    ).classes('w-full')
                    
                    api_hostname = ui.input(
                        label='API Hostname',
                        placeholder='e.g., api.prod.example.com'
                    ).classes('w-full')
                    
                    api_ip = ui.input(
                        label='API IP (optional)',
                        placeholder='e.g., 192.168.1.5'
                    ).classes('w-full')
                    
                    wildcard_domain = ui.input(
                        label='Wildcard Apps Domain',
                        placeholder='e.g., apps.prod.example.com'
                    ).classes('w-full')
                    
                    ui.label('Node Records (JSON)').classes('font-semibold mt-4')
                    nodes_json = ui.textarea(
                        value='[]',
                        placeholder='[{"name": "ocp-master-1.prod.example.com", "ip": "192.168.1.10", "type": "master"}]'
                    ).classes('w-full h-32')
                    
                    # Action buttons
                    with ui.row().classes('w-full gap-2'):
                        async def validate():
                            status.set_text('🔍 Validating DNS...')
                            status.classes(remove='text-green-600 text-red-600')
                            status.classes('text-blue-600')
                            
                            try:
                                # Parse inputs
                                try:
                                    nodes = json.loads(nodes_json.value)
                                except (json.JSONDecodeError, ValueError):
                                    nodes = []
                                
                                # Build node maps
                                master_ips = {
                                    n['name']: n['ip'] for n in nodes
                                    if n.get('type') == 'master' and 'name' in n and 'ip' in n
                                }
                                worker_ips = {
                                    n['name']: n['ip'] for n in nodes
                                    if n.get('type') == 'worker' and 'name' in n and 'ip' in n
                                }
                                
                                # Create validator and run validation
                                validator = DNSValidator()
                                results = validator.validate_openshift_cluster(
                                    cluster_name=cluster_name.value,
                                    domain=domain.value,
                                    master_ips=master_ips or None,
                                    worker_ips=worker_ips or None,
                                    api_ip=api_ip.value or None,
                                    api_int_ip=None
                                )
                                
                                self.last_validation_results = results
                                
                                # Display results
                                results_col.clear()
                                with results_col:
                                    self._display_validation_results(results)
                                
                                passed = results['summary']['passed']
                                failed = results['summary']['failed']
                                
                                if failed == 0:
                                    status.set_text(f'✓ Passed: {passed} tests')
                                    status.classes(remove='text-blue-600 text-red-600')
                                    status.classes('text-green-600')
                                else:
                                    status.set_text(f'✗ Failed: {failed} of {passed + failed} tests')
                                    status.classes(remove='text-blue-600 text-green-600')
                                    status.classes('text-red-600')
                            
                            except Exception as e:
                                status.set_text(f'✗ Error: {str(e)[:100]}')
                                status.classes(remove='text-blue-600 text-green-600')
                                status.classes('text-red-600')
                                logger.error(f"Validation error: {e}", exc_info=True)
                        
                        ui.button('🔍 Validate', on_click=validate).classes('flex-1')
                        ui.button('Clear', on_click=lambda: nodes_json.set_value('[]')).classes('flex-1')
                
                # Results panel
                with ui.column().classes('flex-1 gap-2'):
                    ui.label('Results').classes('font-semibold')
                    status = ui.label('Ready').classes('text-sm opacity-75')
                    results_col = ui.column().classes('w-full gap-2')

    def _display_validation_results(self, results: Dict):
        """Display validation test results"""
        summary = results['summary']
        
        # Summary cards
        with ui.row().classes('w-full gap-2'):
            with ui.card().classes('flex-1 p-3 bg-gray-100 dark:bg-gray-800'):
                ui.label(f"Total").classes('text-xs opacity-75')
                ui.label(str(summary['total_tests'])).classes('text-lg font-bold')
            
            with ui.card().classes('flex-1 p-3 bg-green-100 dark:bg-green-900'):
                ui.label(f"Passed").classes('text-xs opacity-75')
                ui.label(str(summary['passed'])).classes('text-lg font-bold text-green-600')
            
            with ui.card().classes('flex-1 p-3 bg-red-100 dark:bg-red-900'):
                ui.label(f"Failed").classes('text-xs opacity-75')
                ui.label(str(summary['failed'])).classes('text-lg font-bold text-red-600')
            
            with ui.card().classes('flex-1 p-3 bg-yellow-100 dark:bg-yellow-900'):
                ui.label(f"Warnings").classes('text-xs opacity-75')
                ui.label(str(summary['warnings'])).classes('text-lg font-bold text-yellow-600')
        
        # Test results table
        if results['results']:
            test_data = []
            for result in results['results']:
                test_data.append({
                    'hostname': result.get('hostname', 'N/A'),
                    'test': result.get('test_type', 'N/A'),
                    'status': result.get('status', 'unknown'),
                    'message': result.get('message', '')[:80]
                })
            
            with ui.table(title='Test Results', rows=test_data, columns=[
                {'name': 'hostname', 'label': 'Hostname', 'field': 'hostname'},
                {'name': 'test', 'label': 'Test', 'field': 'test'},
                {'name': 'status', 'label': 'Status', 'field': 'status'},
                {'name': 'message', 'label': 'Message', 'field': 'message'},
            ]).classes('w-full'):
                pass
        
        # Recommendation
        if summary.get('ready_for_install'):
            ui.label('✓ Ready for OpenShift installation').classes(
                'p-3 bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-300 rounded'
            )
        else:
            ui.label('✗ Fix failed tests before installation').classes(
                'p-3 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 rounded'
            )

    def _build_updater_panel(self):
        """DNS record synchronization panel"""
        with ui.card().classes('w-full'):
            ui.label('🔄 DNS Record Synchronization').classes('font-semibold')
            ui.label('Update Active Directory DNS from infrastructure inventory').classes('text-sm opacity-75')
            
            with ui.row().classes('w-full gap-4'):
                # Configuration
                with ui.column().classes('flex-1 gap-2'):
                    ui.label('Configuration').classes('font-semibold')
                    
                    provider_select = ui.select(
                        options={'ad': 'Active Directory DNS', 'infoblox': 'Infoblox (TODO)'},
                        value='ad',
                        label='DNS Provider'
                    ).classes('w-full')
                    
                    ui.label('Inventory Sources').classes('font-semibold mt-4')
                    
                    openshift_file = ui.input(
                        label='OpenShift Inventory',
                        value='inventories/openshift.yaml',
                        placeholder='inventories/openshift.yaml'
                    ).classes('w-full')
                    
                    intersight_file = ui.input(
                        label='Intersight Inventory (optional)',
                        value='inventories/intersight.yaml',
                        placeholder='inventories/intersight.yaml'
                    ).classes('w-full')
                    
                    everpure_file = ui.input(
                        label='EveryPure Inventory (optional)',
                        value='inventories/everpure.yaml',
                        placeholder='inventories/everpure.yaml'
                    ).classes('w-full')
                    
                    # Action buttons
                    with ui.row().classes('w-full gap-2'):
                        async def test_connection():
                            status.set_text('🔗 Testing connection...')
                            status.classes(remove='text-green-600 text-red-600')
                            status.classes('text-blue-600')
                            
                            try:
                                provider_config = self.config.get('providers', {}).get(provider_select.value)
                                if not provider_config:
                                    raise ValueError(f'Provider {provider_select.value} not configured in dns_config.yaml')
                                
                                if provider_select.value == 'ad':
                                    provider = ActiveDirectoryProvider(provider_config)
                                    provider.authenticate()
                                    status.set_text('✓ Connected to Active Directory')
                                    status.classes(remove='text-blue-600 text-red-600')
                                    status.classes('text-green-600')
                                else:
                                    raise NotImplementedError(f'{provider_select.value} not yet implemented')
                            
                            except Exception as e:
                                status.set_text(f'✗ Failed: {str(e)[:80]}')
                                status.classes(remove='text-blue-600 text-green-600')
                                status.classes('text-red-600')
                                logger.error(f"Connection error: {e}")
                        
                        async def run_dry_run():
                            status.set_text('🔍 Running dry-run...')
                            status.classes(remove='text-green-600 text-red-600')
                            status.classes('text-blue-600')
                            
                            try:
                                # Parse inventory
                                parser = InventoryParser(logger)
                                inventory_config = {
                                    'openshift': openshift_file.value,
                                    'intersight': intersight_file.value,
                                    'everpure': everpure_file.value
                                }
                                desired_records = parser.parse_all_sources(inventory_config)
                                
                                # Get provider
                                provider_config = self.config.get('providers', {}).get(provider_select.value)
                                if provider_select.value == 'ad':
                                    provider = ActiveDirectoryProvider(provider_config)
                                    provider.authenticate()
                                
                                # Get actual records
                                zones = set(r.zone for r in desired_records)
                                actual_records = set()
                                for zone in zones:
                                    actual_records.update(provider.get_records(zone))
                                
                                # Compare
                                comparator = DNSComparator(logger)
                                missing, stale, matching = comparator.compare(desired_records, actual_records)
                                
                                self.last_update_results = {
                                    'missing': missing,
                                    'stale': stale,
                                    'matching': matching
                                }
                                
                                # Display results
                                results_col.clear()
                                with results_col:
                                    self._display_updater_results(missing, stale, matching)
                                
                                total = len(matching) + len(missing) + len(stale)
                                status.set_text(f'✓ Dry-run complete: {len(matching)}/{total} matching')
                                status.classes(remove='text-blue-600 text-red-600')
                                status.classes('text-green-600')
                            
                            except Exception as e:
                                status.set_text(f'✗ Error: {str(e)[:80]}')
                                status.classes(remove='text-blue-600 text-green-600')
                                status.classes('text-red-600')
                                logger.error(f"Dry-run error: {e}", exc_info=True)
                        
                        ui.button('🔗 Test', on_click=test_connection).classes('flex-1')
                        ui.button('🔍 Dry-Run', on_click=run_dry_run).classes('flex-1')
                
                # Results
                with ui.column().classes('flex-1 gap-2'):
                    ui.label('Update Summary').classes('font-semibold')
                    status = ui.label('Ready').classes('text-sm opacity-75')
                    results_col = ui.column().classes('w-full gap-2')

    def _display_updater_results(self, missing, stale, matching):
        """Display DNS update results"""
        # Summary cards
        with ui.row().classes('w-full gap-2'):
            with ui.card().classes('flex-1 p-3 bg-green-100 dark:bg-green-900'):
                ui.label('Matching').classes('text-xs opacity-75')
                ui.label(str(len(matching))).classes('text-lg font-bold text-green-600')
            
            with ui.card().classes('flex-1 p-3 bg-red-100 dark:bg-red-900'):
                ui.label('Missing').classes('text-xs opacity-75')
                ui.label(str(len(missing))).classes('text-lg font-bold text-red-600')
            
            with ui.card().classes('flex-1 p-3 bg-yellow-100 dark:bg-yellow-900'):
                ui.label('Stale').classes('text-xs opacity-75')
                ui.label(str(len(stale))).classes('text-lg font-bold text-yellow-600')
        
        # Records tables
        if missing:
            ui.label('+ Missing Records (would be created)').classes('font-semibold mt-4 text-red-600')
            missing_rows = [
                {'hostname': r.hostname, 'ip': r.ip_address, 'zone': r.zone}
                for r in sorted(missing, key=lambda x: x.hostname)[:10]
            ]
            with ui.table(rows=missing_rows, columns=[
                {'name': 'hostname', 'label': 'Hostname', 'field': 'hostname'},
                {'name': 'ip', 'label': 'IP', 'field': 'ip'},
                {'name': 'zone', 'label': 'Zone', 'field': 'zone'},
            ]).classes('w-full'):
                pass
            if len(missing) > 10:
                ui.label(f'... and {len(missing) - 10} more').classes('text-xs opacity-50')
        
        if stale:
            ui.label('- Stale Records (would be deleted)').classes('font-semibold mt-4 text-yellow-600')
            stale_rows = [
                {'hostname': r.hostname, 'ip': r.ip_address, 'zone': r.zone}
                for r in sorted(stale, key=lambda x: x.hostname)[:10]
            ]
            with ui.table(rows=stale_rows, columns=[
                {'name': 'hostname', 'label': 'Hostname', 'field': 'hostname'},
                {'name': 'ip', 'label': 'IP', 'field': 'ip'},
                {'name': 'zone', 'label': 'Zone', 'field': 'zone'},
            ]).classes('w-full'):
                pass
            if len(stale) > 10:
                ui.label(f'... and {len(stale) - 10} more').classes('text-xs opacity-50')

    def _build_status_panel(self):
        """System status and configuration overview"""
        with ui.card().classes('w-full'):
            ui.label('📊 Status').classes('font-semibold')
            
            # Configuration status
            with ui.row().classes('w-full gap-2'):
                with ui.card().classes('flex-1 p-3 bg-blue-100 dark:bg-blue-900'):
                    ui.label('DNS Providers').classes('text-xs opacity-75')
                    providers = list(self.config.get('providers', {}).keys())
                    ui.label(f'{len(providers)} configured').classes('font-bold')
                    for p in providers[:3]:
                        ui.label(f'  • {p}').classes('text-xs')
                
                with ui.card().classes('flex-1 p-3 bg-green-100 dark:bg-green-900'):
                    ui.label('Inventory Sources').classes('text-xs opacity-75')
                    sources = list(self.config.get('inventory', {}).keys())
                    ui.label(f'{len(sources)} configured').classes('font-bold')
                    for s in sources[:3]:
                        ui.label(f'  • {s}').classes('text-xs')
                
                with ui.card().classes('flex-1 p-3 bg-purple-100 dark:bg-purple-900'):
                    ui.label('Vault Integration').classes('text-xs opacity-75')
                    vault_enabled = self.config.get('vault', {}).get('enabled', False)
                    status_text = '✓ Enabled' if vault_enabled else '✗ Disabled'
                    color = 'text-green-600' if vault_enabled else 'text-red-600'
                    ui.label(status_text).classes(f'font-bold {color}')
            
            # Last results
            ui.label('Last Operations').classes('font-semibold mt-4')
            
            with ui.row().classes('w-full gap-2'):
                if self.last_validation_results:
                    with ui.card().classes('flex-1 p-3'):
                        ui.label('Last Validation').classes('font-semibold text-sm')
                        summary = self.last_validation_results['summary']
                        passed = summary.get('passed', 0)
                        failed = summary.get('failed', 0)
                        ui.label(f"✓ {passed} passed, ✗ {failed} failed").classes('text-xs opacity-75')
                
                if self.last_update_results:
                    with ui.card().classes('flex-1 p-3'):
                        ui.label('Last Sync Check').classes('font-semibold text-sm')
                        results = self.last_update_results
                        total = len(results['matching']) + len(results['missing']) + len(results['stale'])
                        ui.label(f"✓ {len(results['matching'])}/{total} matching").classes('text-xs opacity-75')
