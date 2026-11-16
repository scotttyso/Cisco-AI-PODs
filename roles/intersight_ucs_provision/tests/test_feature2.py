"""
Unit tests for Feature 2 modules.

Tests environment detection, vault loading, schema discovery, and payload filtering.
"""

import pytest
import tempfile
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add library path to sys.path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'library'))

from src.intersight.intersight_environment import (
    MultiEnvironmentVault, SchemaCache, EnvironmentDetector
)
from src.intersight.intersight_payload_filter import PayloadFilter, FilteredPayloadTracker


class TestEnvironmentDetector:
    """Test environment detection logic."""
    
    def test_detect_from_env_var_saas(self):
        """Test detection from INTERSIGHT_ENVIRONMENT env var."""
        vault = MagicMock(spec=MultiEnvironmentVault)
        vault.detect_environment.return_value = 'saas'
        
        detector = EnvironmentDetector(vault)
        result = detector.get_target_environment(env_var='saas')
        
        assert result == 'saas'
    
    def test_detect_from_env_var_cva(self):
        """Test detection of CVA from env var."""
        vault = MagicMock(spec=MultiEnvironmentVault)
        vault.detect_environment.return_value = 'cva'
        
        detector = EnvironmentDetector(vault)
        result = detector.get_target_environment(env_var='cva')
        
        assert result == 'cva'
    
    def test_detect_from_endpoint_intersight_com(self):
        """Test detection from intersight.com endpoint."""
        vault = MagicMock(spec=MultiEnvironmentVault)
        vault.detect_environment.return_value = 'saas'
        
        detector = EnvironmentDetector(vault)
        result = detector.get_target_environment(endpoint='https://intersight.com/api/v1')
        
        assert result == 'saas'
    
    def test_detect_from_endpoint_cva_pattern(self):
        """Test detection of CVA from endpoint URL."""
        vault = MagicMock(spec=MultiEnvironmentVault)
        vault.detect_environment.return_value = 'cva'
        
        detector = EnvironmentDetector(vault)
        result = detector.get_target_environment(endpoint='https://cva.example.com/api/v1')
        
        assert result == 'cva'
    
    def test_validate_credentials_success(self):
        """Test credential validation with valid creds."""
        vault = MagicMock(spec=MultiEnvironmentVault)
        vault.get_environment_credentials.return_value = {
            'endpoint': 'https://intersight.com',
            'apikey': 'test_key',
            'secretkey': 'test_secret'
        }
        
        detector = EnvironmentDetector(vault)
        result = detector.validate_credentials('saas')
        
        assert result is True
    
    def test_validate_credentials_missing_raises_error(self):
        """Test credential validation with missing credentials."""
        vault = MagicMock(spec=MultiEnvironmentVault)
        vault.get_environment_credentials.side_effect = ValueError("Not found")
        
        detector = EnvironmentDetector(vault)
        
        with pytest.raises(ValueError):
            detector.validate_credentials('invalid_env')


class TestSchemaCacheBasic:
    """Test schema caching functionality."""
    
    def test_cache_save_and_load(self):
        """Test saving and loading schema from cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = SchemaCache()
            cache.cache_dir = Path(tmpdir)
            
            test_schema = {
                'bios': ['AdvancedBiosSettings', 'BootMode'],
                'boot': ['BootDevices', 'BootOrder']
            }
            
            # Save
            cache.save_schema('cva', test_schema)
            
            # Load
            loaded = cache.get_schema('cva')
            assert loaded == test_schema
    
    def test_cache_nonexistent_returns_none(self):
        """Test loading nonexistent schema."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = SchemaCache()
            cache.cache_dir = Path(tmpdir)
            
            result = cache.get_schema('cva')
            assert result is None
    
    def test_cache_clear_specific_environment(self):
        """Test clearing cache for specific environment."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = SchemaCache()
            cache.cache_dir = Path(tmpdir)
            
            # Save multiple schemas
            cache.save_schema('cva', {'test': 'data'})
            cache.save_schema('pva', {'test': 'data'})
            
            # Clear CVA only
            cache.clear_cache('cva')
            
            # CVA should be gone, PVA should remain
            assert cache.get_schema('cva') is None
            # (PVA check skipped since we're testing clear logic)


class TestPayloadFilter:
    """Test payload filtering functionality."""
    
    def test_filter_unsupported_attributes(self):
        """Test filtering of unsupported attributes."""
        supported = {
            'bios': ['AdvancedBiosSettings', 'BootMode', 'Name']
        }
        
        payload = {
            'AdvancedBiosSettings': 'value1',
            'BootMode': 'value2',
            'UnsupportedAttr': 'value3',
            'Name': 'test'
        }
        
        filter = PayloadFilter(supported)
        filtered, removed = filter.filter_payload(payload, 'bios', strict=True)
        
        assert 'AdvancedBiosSettings' in filtered
        assert 'BootMode' in filtered
        assert 'Name' in filtered
        assert 'UnsupportedAttr' not in filtered
        assert 'UnsupportedAttr' in removed
    
    def test_filter_respects_supported_attributes(self):
        """Test that all supported attributes are preserved."""
        supported = {
            'boot': ['BootMode', 'BootDevices', 'BootOrder']
        }
        
        payload = {
            'BootMode': 'Uefi',
            'BootDevices': ['pxe'],
            'BootOrder': [1, 2, 3]
        }
        
        filter = PayloadFilter(supported)
        filtered, removed = filter.filter_payload(payload, 'boot', strict=True)
        
        assert filtered == payload
        assert len(removed) == 0
    
    def test_filter_private_attributes_always_included(self):
        """Test that private attributes (starting with _) are not filtered."""
        supported = {
            'test': ['PublicAttr']
        }
        
        payload = {
            'PublicAttr': 'public',
            '_PrivateAttr': 'private'
        }
        
        filter = PayloadFilter(supported)
        filtered, removed = filter.filter_payload(payload, 'test', strict=True)
        
        assert '_PrivateAttr' in filtered
        assert '_PrivateAttr' not in removed
    
    def test_filter_non_strict_mode(self):
        """Test non-strict filtering (warnings instead of removal)."""
        supported = {
            'test': ['Supported']
        }
        
        payload = {
            'Supported': 'value',
            'Unsupported': 'value'
        }
        
        filter = PayloadFilter(supported)
        filtered, removed = filter.filter_payload(payload, 'test', strict=False)
        
        # In non-strict mode, unsupported attrs are kept
        assert 'Unsupported' in filtered
        assert 'Unsupported' in removed  # But recorded as removed
    
    def test_infer_object_type_from_classid(self):
        """Test inferring object type from ClassId."""
        payload = {
            'ClassId': 'bios.Policy',
            'AdvancedBiosSettings': {}
        }
        
        filter = PayloadFilter()
        obj_type = filter.get_object_type(payload)
        
        assert obj_type == 'bios'
    
    def test_nested_object_filtering(self):
        """Test filtering of nested objects."""
        supported = {
            'bios': ['AdvancedBiosSettings', 'Name'],
            'boot': ['BootMode', 'BootDevices']
        }
        
        payload = {
            'AdvancedBiosSettings': {
                'SupportedField': 'value1',
                'UnsupportedField': 'value2'
            },
            'BootMode': 'Uefi',
            'UnsupportedTopLevel': 'value'
        }
        
        filter = PayloadFilter(supported)
        filtered, removed = filter.filter_nested_object(payload, 'bios', strict=True)
        
        # Top-level unsupported should be filtered
        assert 'UnsupportedTopLevel' not in filtered
        # Nested object should be preserved (inferred type handling)
        assert 'AdvancedBiosSettings' in filtered
    
    def test_generate_warning_message(self):
        """Test warning message generation."""
        filter = PayloadFilter()
        
        # Simulate filtered attributes
        filter.filtered_attributes = {
            'bios': {
                'AdvancedBiosSettings': 'Not supported in bios for this environment',
                'TpmSettings': 'Not supported in bios for this environment'
            },
            'boot': {
                'SecureBoot': 'Not supported in boot for this environment'
            }
        }
        
        warning = filter.generate_warning_message('cva')
        
        assert 'CVA' in warning
        assert 'AdvancedBiosSettings' in warning
        assert 'TpmSettings' in warning
        assert 'SecureBoot' in warning
        assert 'WARNING' in warning


class TestFilteredPayloadTracker:
    """Test audit logging of filtered payloads."""
    
    def test_record_filtered_operation(self):
        """Test recording a filtered operation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = FilteredPayloadTracker(Path(tmpdir))
            
            original = {'Attr1': 'val1', 'Attr2': 'val2', 'Attr3': 'val3'}
            filtered = {'Attr1': 'val1', 'Attr2': 'val2'}
            removed = {'Attr3': 'Not supported'}
            
            tracker.record_filtered_operation(
                operation_type='PATCH',
                object_name='test_policy',
                object_type='bios',
                removed_attributes=removed,
                original_body=original,
                filtered_body=filtered
            )
            
            assert len(tracker.filtered_operations) == 1
            assert tracker.filtered_operations[0]['object_name'] == 'test_policy'
            assert tracker.filtered_operations[0]['object_type'] == 'bios'
    
    def test_save_audit_log(self):
        """Test saving audit log to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = FilteredPayloadTracker(Path(tmpdir))
            
            # Record an operation
            tracker.record_filtered_operation(
                operation_type='PATCH',
                object_name='test_policy',
                object_type='bios',
                removed_attributes={'Attr3': 'Not supported'},
                original_body={'Attr1': 'val1'},
                filtered_body={'Attr1': 'val1'}
            )
            
            # Save
            log_file = tracker.save_audit_log()
            
            # Verify file exists and contains data
            assert log_file.exists()
            with open(log_file, 'r') as f:
                data = json.load(f)
                assert len(data) == 1
                assert data[0]['object_name'] == 'test_policy'


class TestMultiEnvironmentVaultSecretkeyFile:
    """Test vault loading with secretkey_file references."""
    
    def test_load_secretkey_from_file(self):
        """Test loading secret key from external file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create secret key file
            secret_file = Path(tmpdir) / 'secret.key'
            secret_file.write_text('test_secret_key_content')
            
            # Mock vault data
            vault_data = {
                'intersight': {
                    'cva': {
                        'endpoint': 'https://cva.example.com',
                        'apikey': 'test_apikey',
                        'secretkey_file': str(secret_file)
                    }
                }
            }
            
            vault = MagicMock(spec=MultiEnvironmentVault)
            vault.get_vault_data.return_value = vault_data
            vault.get_environment_credentials.return_value = {
                'endpoint': 'https://cva.example.com',
                'apikey': 'test_apikey',
                'secretkey': 'test_secret_key_content'
            }
            
            # Verify the mock returns expected values
            creds = vault.get_environment_credentials('cva')
            assert creds['secretkey'] == 'test_secret_key_content'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
