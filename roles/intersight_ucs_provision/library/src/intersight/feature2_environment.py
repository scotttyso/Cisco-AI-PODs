"""
Multi-environment credential and schema management for Feature 2.

Handles loading credentials for different Intersight environments (SaaS, CVA, PVA)
and managing cached API schemas for attribute filtering.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from dotmap import DotMap
import yaml
from datetime import datetime


class MultiEnvironmentVault:
    """Load and manage credentials for multiple Intersight environments."""

    def __init__(self, vault_path: Optional[str] = None, 
                 vault_password_path: Optional[str] = None):
        """Initialize vault loader.
        
        Args:
            vault_path: Path to vault file (default: ~/.config/cisco-ai-pods/vault.yaml)
            vault_password_path: Path to vault password file
        """
        if not vault_path:
            vault_path = Path.home() / '.config' / 'cisco-ai-pods' / 'vault.yaml'
        if not vault_password_path:
            vault_password_path = Path.home() / '.config' / 'cisco-ai-pods' / 'vault-password'
        
        self.vault_path = Path(vault_path)
        self.vault_password_path = Path(vault_password_path)
        self._vault_data = None
    
    def _decrypt_vault(self) -> Dict[str, Any]:
        """Decrypt vault file using ansible-vault."""
        if not self.vault_path.exists():
            raise FileNotFoundError(f"Vault file not found: {self.vault_path}")
        if not self.vault_password_path.exists():
            raise FileNotFoundError(f"Vault password file not found: {self.vault_password_path}")
        
        try:
            result = subprocess.run(
                ['ansible-vault', 'view', str(self.vault_path), 
                 '--vault-password-file', str(self.vault_password_path)],
                capture_output=True,
                text=True,
                check=True
            )
            return yaml.safe_load(result.stdout) or {}
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to decrypt vault: {e.stderr}")
        except Exception as e:
            raise RuntimeError(f"Error loading vault credentials: {e}")
    
    def get_vault_data(self) -> Dict[str, Any]:
        """Get decrypted vault data (cached)."""
        if self._vault_data is None:
            self._vault_data = self._decrypt_vault()
        return self._vault_data
    
    def get_environment_credentials(self, environment: str) -> Dict[str, str]:
        """Get credentials for a specific environment.
        
        Args:
            environment: Environment name ('saas', 'cva', 'pva')
            
        Returns:
            Dict with 'endpoint', 'apikey', 'secretkey'
        """
        vault_data = self.get_vault_data()
        intersight_config = vault_data.get('intersight', {})
        env_config = intersight_config.get(environment)
        
        if not env_config:
            raise ValueError(f"No credentials found for environment: {environment}")
        
        # Handle secretkey_file reference
        secretkey = env_config.get('secretkey', '')
        secretkey_file = env_config.get('secretkey_file')
        
        if secretkey_file:
            # Load secret key from file
            secret_path = Path(secretkey_file)
            if not secret_path.exists():
                # Try expanding ~ if present
                if '~' in secretkey_file:
                    secret_path = Path(secretkey_file).expanduser()
            
            if secret_path.exists():
                try:
                    with open(secret_path, 'r') as f:
                        secretkey = f.read().strip()
                except Exception as e:
                    raise RuntimeError(f"Failed to read secretkey_file: {e}")
            else:
                raise FileNotFoundError(f"Secret key file not found: {secretkey_file}")
        
        return {
            'endpoint': env_config.get('endpoint', ''),
            'apikey': env_config.get('apikey', ''),
            'secretkey': secretkey
        }
    
    def detect_environment(self, endpoint: Optional[str] = None, 
                          env_var: Optional[str] = None) -> str:
        """Detect target environment from endpoint or environment variable.
        
        Args:
            endpoint: API endpoint URL
            env_var: Environment variable value (INTERSIGHT_ENVIRONMENT)
            
        Returns:
            Environment name: 'saas', 'cva', or 'pva'
        """
        # Priority 1: Environment variable
        if env_var and env_var.lower() in ['saas', 'cva', 'pva']:
            return env_var.lower()
        
        # Priority 2: Endpoint URL pattern matching
        if endpoint:
            endpoint_lower = endpoint.lower()
            if 'intersight.com' in endpoint_lower:
                return 'saas'
            elif 'cva' in endpoint_lower:
                return 'cva'
            elif 'pva' in endpoint_lower:
                return 'pva'
        
        # Default to SaaS
        return 'saas'


class SchemaCache:
    """Manage caching of API schemas for attribute filtering."""
    
    CACHE_DIR = Path.home() / '.cache' / 'cisco-ai-pods' / 'schemas'
    
    def __init__(self):
        """Initialize schema cache."""
        self.cache_dir = self.CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_file(self, environment: str, api_version: str = 'v1') -> Path:
        """Get cache file path for environment."""
        return self.cache_dir / f"{environment}_{api_version}_schema.json"
    
    def get_schema(self, environment: str, api_version: str = 'v1') -> Optional[Dict[str, Any]]:
        """Load cached schema if it exists.
        
        Args:
            environment: Environment name ('saas', 'cva', 'pva')
            api_version: API version (default: 'v1')
            
        Returns:
            Cached schema dict or None if not cached
        """
        cache_file = self._get_cache_file(environment, api_version)
        
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except Exception:
                return None
        
        return None
    
    def save_schema(self, environment: str, schema: Dict[str, Any], 
                    api_version: str = 'v1') -> None:
        """Save schema to cache.
        
        Args:
            environment: Environment name
            schema: Schema dict to cache
            api_version: API version
        """
        cache_file = self._get_cache_file(environment, api_version)
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(schema, f, indent=2)
        except Exception as e:
            print(f"Warning: Failed to cache schema: {e}")
    
    def clear_cache(self, environment: Optional[str] = None) -> None:
        """Clear cached schemas.
        
        Args:
            environment: Specific environment to clear, or None for all
        """
        if environment:
            # Clear specific environment
            cache_file = self._get_cache_file(environment)
            if cache_file.exists():
                cache_file.unlink()
        else:
            # Clear all schemas
            if self.cache_dir.exists():
                import shutil
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)


class EnvironmentDetector:
    """Detect and validate target Intersight environment."""
    
    def __init__(self, vault: MultiEnvironmentVault):
        """Initialize detector.
        
        Args:
            vault: MultiEnvironmentVault instance
        """
        self.vault = vault
    
    def get_target_environment(self, 
                              env_var: Optional[str] = None,
                              endpoint: Optional[str] = None,
                              apikey: Optional[str] = None) -> str:
        """Determine target environment with priority order.
        
        Priority:
        1. INTERSIGHT_ENVIRONMENT env var
        2. API endpoint URL pattern
        3. API key pattern (if available in vault)
        4. Default to SaaS
        
        Args:
            env_var: INTERSIGHT_ENVIRONMENT value
            endpoint: API endpoint URL
            apikey: API key ID (for validation)
            
        Returns:
            Environment name: 'saas', 'cva', or 'pva'
        """
        return self.vault.detect_environment(endpoint, env_var)
    
    def validate_credentials(self, environment: str) -> bool:
        """Validate credentials exist for environment.
        
        Args:
            environment: Environment name
            
        Returns:
            True if credentials found, raises ValueError otherwise
        """
        try:
            creds = self.vault.get_environment_credentials(environment)
            required = ['endpoint', 'apikey', 'secretkey']
            for key in required:
                if not creds.get(key):
                    raise ValueError(f"Missing {key} for {environment}")
            return True
        except ValueError as e:
            raise ValueError(f"Invalid credentials for {environment}: {e}")
