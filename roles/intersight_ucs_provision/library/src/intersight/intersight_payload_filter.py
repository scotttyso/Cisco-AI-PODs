"""
Payload filtering for Feature 2.

Filters unsupported attributes from API payloads before sending to CVA/PVA.
"""

from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import json
from dotmap import DotMap


class PayloadFilter:
    """Filter unsupported attributes from API payloads."""
    
    def __init__(self, supported_attributes: Optional[Dict[str, List[str]]] = None):
        """Initialize payload filter.
        
        Args:
            supported_attributes: Dict mapping object_type -> list of supported attribute names
        """
        self.supported_attributes = supported_attributes or {}
        self.filtered_attributes = {}  # Track what was filtered
    
    def set_supported_attributes(self, attributes: Dict[str, List[str]]) -> None:
        """Set the supported attributes mapping.
        
        Args:
            attributes: Dict of object_type -> supported attribute names
        """
        self.supported_attributes = attributes
        self.filtered_attributes = {}  # Reset tracking
    
    def get_object_type(self, api_body: Dict[str, Any]) -> Optional[str]:
        """Infer object type from API body.
        
        Args:
            api_body: API request body
            
        Returns:
            Object type name (e.g., 'bios', 'boot', etc.) or None
        """
        # Try to extract from ClassId
        class_id = api_body.get('ClassId', '')
        if class_id:
            # Format: "bios.Policy" -> "bios"
            return class_id.split('.')[0].lower()
        
        # Try to infer from object properties
        if 'BootMode' in api_body or 'BootDevices' in api_body:
            return 'boot'
        elif 'Settings' in api_body or 'AdvancedBiosSettings' in api_body:
            return 'bios'
        elif 'MacPools' in api_body or 'IqnPools' in api_body:
            return 'generic'
        
        return None
    
    def filter_payload(self, api_body: Dict[str, Any], 
                      object_type: Optional[str] = None,
                      strict: bool = True) -> Tuple[Dict[str, Any], Dict[str, List[str]]]:
        """Filter unsupported attributes from payload.
        
        Args:
            api_body: API request body to filter
            object_type: Object type (inferred if not provided)
            strict: If True, remove unsupported attrs; if False, only warn
            
        Returns:
            Tuple of (filtered_body, removed_attributes)
            removed_attributes: Dict of attribute -> reason for removal
        """
        if not object_type:
            object_type = self.get_object_type(api_body)
        
        if not object_type or object_type not in self.supported_attributes:
            # No filter info available, return original
            return api_body, {}
        
        supported = set(self.supported_attributes[object_type])
        filtered_body = {}
        removed = {}
        
        for key, value in api_body.items():
            if key in supported:
                # Attribute is supported, keep it
                filtered_body[key] = value
            elif key.startswith('_'):
                # Private attributes, skip filtering
                filtered_body[key] = value
            else:
                # Unsupported attribute
                if strict:
                    removed[key] = f"Not supported in {object_type} for this environment"
                else:
                    filtered_body[key] = value
                    removed[key] = f"Unsupported but included (non-strict mode)"
        
        # Track what was removed
        if removed and object_type not in self.filtered_attributes:
            self.filtered_attributes[object_type] = {}
        
        for attr, reason in removed.items():
            if object_type not in self.filtered_attributes:
                self.filtered_attributes[object_type] = {}
            self.filtered_attributes[object_type][attr] = reason
        
        return filtered_body, removed
    
    def filter_nested_object(self, obj: Any, object_type: Optional[str] = None,
                            strict: bool = True) -> Tuple[Any, Dict[str, List[str]]]:
        """Filter nested objects recursively.
        
        Args:
            obj: Object to filter (dict, list, or primitive)
            object_type: Object type hint
            strict: If True, remove unsupported attrs
            
        Returns:
            Tuple of (filtered_object, all_removed)
        """
        all_removed = {}
        
        if isinstance(obj, dict):
            filtered_body, removed = self.filter_payload(obj, object_type, strict)
            
            # Recursively filter nested objects
            for key, value in filtered_body.items():
                if isinstance(value, dict):
                    # Try to infer type from key patterns
                    nested_type = self._infer_nested_type(key, value)
                    filtered_body[key], nested_removed = self.filter_nested_object(
                        value, nested_type, strict
                    )
                    all_removed.update(nested_removed)
                elif isinstance(value, list):
                    filtered_list = []
                    for item in value:
                        if isinstance(item, dict):
                            filtered_item, item_removed = self.filter_nested_object(
                                item, None, strict
                            )
                            filtered_list.append(filtered_item)
                            all_removed.update(item_removed)
                        else:
                            filtered_list.append(item)
                    filtered_body[key] = filtered_list
            
            all_removed.update(removed)
            return filtered_body, all_removed
        
        elif isinstance(obj, list):
            filtered_list = []
            for item in obj:
                if isinstance(item, dict):
                    filtered_item, item_removed = self.filter_nested_object(
                        item, object_type, strict
                    )
                    filtered_list.append(filtered_item)
                    all_removed.update(item_removed)
                else:
                    filtered_list.append(item)
            return filtered_list, all_removed
        
        else:
            # Primitive type, return as-is
            return obj, all_removed
    
    def _infer_nested_type(self, key: str, obj: Dict[str, Any]) -> Optional[str]:
        """Infer object type from key name and content.
        
        Args:
            key: Dictionary key name
            obj: The object content
            
        Returns:
            Inferred object type or None
        """
        key_lower = key.lower()
        
        # Key-based inference
        if 'bios' in key_lower:
            return 'bios'
        elif 'boot' in key_lower:
            return 'boot'
        elif 'ethernet' in key_lower or 'eth' in key_lower:
            return 'ethernet'
        elif 'fibre' in key_lower or 'fc' in key_lower:
            return 'fibre_channel'
        elif 'storage' in key_lower:
            return 'storage'
        
        # Try ClassId from object
        if 'ClassId' in obj:
            return self.get_object_type(obj)
        
        return None
    
    def get_removed_summary(self) -> Dict[str, Dict[str, str]]:
        """Get summary of all removed attributes during filtering.
        
        Returns:
            Dict of object_type -> dict of attribute -> reason
        """
        return self.filtered_attributes.copy()
    
    def generate_warning_message(self, environment: str) -> str:
        """Generate user-facing warning about removed attributes.
        
        Args:
            environment: Target environment (e.g., 'cva')
            
        Returns:
            Formatted warning message
        """
        if not self.filtered_attributes:
            return ""
        
        lines = [
            f"\n{'='*80}",
            f"WARNING: Attributes Removed for {environment.upper()} Environment",
            f"{'='*80}\n"
        ]
        
        for obj_type, removed_attrs in sorted(self.filtered_attributes.items()):
            lines.append(f"{obj_type.upper()} Policy/Profile:")
            for attr, reason in sorted(removed_attrs.items()):
                lines.append(f"  - {attr}: {reason}")
            lines.append("")
        
        lines.append(
            "These attributes are not supported by your environment and have been\n"
            "automatically filtered out. Consider updating your environment to the\n"
            "latest version if you need these features.\n"
        )
        lines.append(f"{'='*80}\n")
        
        return "\n".join(lines)


class FilteredPayloadTracker:
    """Track filtered payloads for audit and debugging."""
    
    def __init__(self, log_dir: Optional[Path] = None):
        """Initialize tracker.
        
        Args:
            log_dir: Directory to store filtered payload logs
        """
        if not log_dir:
            log_dir = Path.home() / '.cache' / 'cisco-ai-pods' / 'filtered-payloads'
        
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.filtered_operations = []
    
    def record_filtered_operation(self, operation_type: str, object_name: str,
                                 object_type: str, removed_attributes: Dict[str, str],
                                 original_body: Dict[str, Any],
                                 filtered_body: Dict[str, Any]) -> None:
        """Record a filtered API operation.
        
        Args:
            operation_type: Operation type ('POST', 'PATCH', 'GET')
            object_name: Name of the object being operated on
            object_type: Type of object
            removed_attributes: Dict of removed attributes
            original_body: Original payload
            filtered_body: Filtered payload
        """
        from datetime import datetime
        
        record = {
            'operation_type': operation_type,
            'object_name': object_name,
            'object_type': object_type,
            'removed_attributes': removed_attributes,
            'original_attribute_count': len(original_body),
            'filtered_attribute_count': len(filtered_body),
            'timestamp': datetime.now().isoformat()
        }
        
        self.filtered_operations.append(record)
    
    def save_audit_log(self, filename: str = 'filtered_payloads_audit.json') -> Path:
        """Save audit log of all filtered operations.
        
        Args:
            filename: Name of audit log file
            
        Returns:
            Path to saved log file
        """
        log_file = self.log_dir / filename
        
        try:
            with open(log_file, 'w') as f:
                json.dump(self.filtered_operations, f, indent=2, default=str)
        except Exception as e:
            print(f"Warning: Failed to save audit log: {e}")
        
        return log_file
