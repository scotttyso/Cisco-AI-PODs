"""
Standalone unit tests for Feature 2 modules - no library imports.

Tests core functionality of environment detection, vault loading, schema discovery, and payload filtering.
"""

import pytest
import tempfile
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

# Test PayloadFilter directly
def test_payload_filter_basic():
    """Test basic payload filtering."""
    # Import only the feature module
    sys.path.insert(0, str(Path(__file__).parent.parent / 'library'))
    from src.intersight.feature2_payload_filter import PayloadFilter
    
    supported = {
        'bios': ['AdvancedBiosSettings', 'BootMode', 'Name']
    }
    
    payload = {
        'AdvancedBiosSettings': 'value1',
        'BootMode': 'value2',
        'UnsupportedAttr': 'value3',
        'Name': 'test'
    }
    
    filter_obj = PayloadFilter(supported)
    filtered, removed = filter_obj.filter_payload(payload, 'bios', strict=True)
    
    assert 'AdvancedBiosSettings' in filtered
    assert 'BootMode' in filtered
    assert 'Name' in filtered
    assert 'UnsupportedAttr' not in filtered
    assert 'UnsupportedAttr' in removed


def test_payload_filter_respects_supported():
    """Test that all supported attributes are preserved."""
    sys.path.insert(0, str(Path(__file__).parent.parent / 'library'))
    from src.intersight.feature2_payload_filter import PayloadFilter
    
    supported = {
        'boot': ['BootMode', 'BootDevices', 'BootOrder']
    }
    
    payload = {
        'BootMode': 'Uefi',
        'BootDevices': ['pxe'],
        'BootOrder': [1, 2, 3]
    }
    
    filter_obj = PayloadFilter(supported)
    filtered, removed = filter_obj.filter_payload(payload, 'boot', strict=True)
    
    assert filtered == payload
    assert len(removed) == 0


def test_payload_filter_private_attributes():
    """Test that private attributes (starting with _) are not filtered."""
    sys.path.insert(0, str(Path(__file__).parent.parent / 'library'))
    from src.intersight.feature2_payload_filter import PayloadFilter
    
    supported = {
        'test': ['PublicAttr']
    }
    
    payload = {
        'PublicAttr': 'public',
        '_PrivateAttr': 'private'
    }
    
    filter_obj = PayloadFilter(supported)
    filtered, removed = filter_obj.filter_payload(payload, 'test', strict=True)
    
    assert '_PrivateAttr' in filtered
    assert '_PrivateAttr' not in removed


def test_infer_object_type_from_classid():
    """Test inferring object type from ClassId."""
    sys.path.insert(0, str(Path(__file__).parent.parent / 'library'))
    from src.intersight.feature2_payload_filter import PayloadFilter
    
    payload = {
        'ClassId': 'bios.Policy',
        'AdvancedBiosSettings': {}
    }
    
    filter_obj = PayloadFilter()
    obj_type = filter_obj.get_object_type(payload)
    
    assert obj_type == 'bios'


def test_generate_warning_message():
    """Test warning message generation."""
    sys.path.insert(0, str(Path(__file__).parent.parent / 'library'))
    from src.intersight.feature2_payload_filter import PayloadFilter
    
    filter_obj = PayloadFilter()
    
    # Simulate filtered attributes
    filter_obj.filtered_attributes = {
        'bios': {
            'AdvancedBiosSettings': 'Not supported in bios for this environment',
            'TpmSettings': 'Not supported in bios for this environment'
        },
        'boot': {
            'SecureBoot': 'Not supported in boot for this environment'
        }
    }
    
    warning = filter_obj.generate_warning_message('cva')
    
    assert 'CVA' in warning
    assert 'AdvancedBiosSettings' in warning
    assert 'TpmSettings' in warning
    assert 'SecureBoot' in warning
    assert 'WARNING' in warning


def test_schema_cache_save_and_load():
    """Test saving and loading schema from cache."""
    sys.path.insert(0, str(Path(__file__).parent.parent / 'library'))
    from src.intersight.feature2_environment import SchemaCache
    
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


def test_schema_cache_nonexistent():
    """Test loading nonexistent schema."""
    sys.path.insert(0, str(Path(__file__).parent.parent / 'library'))
    from src.intersight.feature2_environment import SchemaCache
    
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = SchemaCache()
        cache.cache_dir = Path(tmpdir)
        
        result = cache.get_schema('cva')
        assert result is None


def test_environment_detector():
    """Test environment detection."""
    sys.path.insert(0, str(Path(__file__).parent.parent / 'library'))
    from src.intersight.feature2_environment import EnvironmentDetector, MultiEnvironmentVault
    
    vault = MagicMock(spec=MultiEnvironmentVault)
    vault.detect_environment.return_value = 'cva'
    
    detector = EnvironmentDetector(vault)
    result = detector.get_target_environment(env_var='cva')
    
    assert result == 'cva'


def test_filtered_payload_tracker():
    """Test audit logging of filtered payloads."""
    sys.path.insert(0, str(Path(__file__).parent.parent / 'library'))
    from src.intersight.feature2_payload_filter import FilteredPayloadTracker
    
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
        
        # Test save audit log
        log_file = tracker.save_audit_log()
        assert log_file.exists()
        
        with open(log_file, 'r') as f:
            data = json.load(f)
            assert len(data) == 1
            assert data[0]['object_name'] == 'test_policy'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
