"""
CVA/PVA payload filtering integration for Intersight deployment.

This module integrates the intersight_payload_filter with the deployment
process, applying attribute filtering when targeting CVA or PVA environments.
"""

from typing import Dict, Any, Tuple, Optional
from copy import deepcopy


class PayloadFilteringIntegration:
    """Integrate payload filtering into deployment workflow."""

    def __init__(self, kwargs: Optional[Dict[str, Any]] = None):
        """Initialize filtering integration.
        
        Args:
            kwargs: Deployment kwargs with environment and schema_cache info
        """
        self.kwargs = kwargs
        self.environment = kwargs.get('intersight_environment', 'saas') if kwargs else 'saas'
        self.schema_cache = kwargs.get('schema_cache') if kwargs else None
        self.payload_filter = None
        self.filtered_summary = {}
        
        # Initialize payload filter if CVA/PVA and schema cache available
        if self.environment != 'saas' and self.schema_cache:
            self._initialize_filter()
    
    def _initialize_filter(self):
        """Initialize payload filter with schema for target environment."""
        try:
            from src.intersight.intersight_payload_filter import PayloadFilter
            
            # Try to load cached schema
            schema = self.schema_cache.get_schema(self.environment)
            if schema:
                self.payload_filter = PayloadFilter(schema)
            else:
                # Schema not cached, could load from API here
                self.payload_filter = PayloadFilter()
        except Exception:
            # If filtering initialization fails, proceed without filtering
            pass
    
    def should_filter(self) -> bool:
        """Check if filtering should be applied.
        
        Returns:
            True if filtering is enabled and configured
        """
        return self.environment != 'saas' and self.payload_filter is not None
    
    def filter_payload(self, payload: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """Filter unsupported attributes from payload.
        
        Args:
            payload: Original API request body
            
        Returns:
            Tuple of (filtered_payload, removed_attributes)
        """
        if not self.should_filter():
            return payload, {}
        
        try:
            filtered, removed = self.payload_filter.filter_payload(
                payload,
                strict=True  # Remove unsupported attributes for CVA/PVA
            )
            
            # Track filtered attributes
            if removed:
                payload_name = payload.get('Name', 'unknown')
                if payload_name not in self.filtered_summary:
                    self.filtered_summary[payload_name] = removed
            
            return filtered, removed
        except Exception:
            # If filtering fails for specific payload, return original
            return payload, {}
    
    def get_filtered_summary(self) -> Dict[str, Any]:
        """Get summary of all filtered attributes.
        
        Returns:
            Dict of object_name -> removed_attributes
        """
        return self.filtered_summary
    
    def should_log_filtering(self) -> bool:
        """Check if any filtering occurred that should be logged.
        
        Returns:
            True if filtering occurred
        """
        return len(self.filtered_summary) > 0


def apply_payload_filtering(payload: Dict[str, Any],
                            environment: str = 'saas',
                            payload_filter: Optional[Any] = None) -> Dict[str, Any]:
    """Convenience function to filter a single payload.
    
    Args:
        payload: Original payload body
        environment: Target environment ('saas', 'cva', 'pva')
        payload_filter: Optional PayloadFilter instance
        
    Returns:
        Filtered payload (or original if filtering not applicable)
    """
    if environment == 'saas' or payload_filter is None:
        return payload
    
    try:
        filtered, _ = payload_filter.filter_payload(payload, strict=True)
        return filtered
    except Exception:
        return payload
