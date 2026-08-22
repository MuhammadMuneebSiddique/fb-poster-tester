"""
Configuration Manager Module
Handles secure local storage of user configuration (Access Token, Page ID, App ID, etc.)
Supports multiple Facebook Pages (up to 5 per license)
"""

import os
import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from pathlib import Path


def _get_config_dir() -> str:
    """
    Get the configuration directory path.
    Uses a consistent, absolute path based on the script location.
    Works across Windows, Linux, and Termux/Android.
    """
    # Try to find the project root (where main.py is located)
    # Walk up from this file's location to find main.py
    current_dir = Path(__file__).resolve()

    # Look for main.py in parent directories
    for parent in current_dir.parents:
        if (parent / 'main.py').exists():
            return str(parent)

    # Fallback: use a dedicated config directory in user's home
    home_config = Path.home() / '.fb_poster'
    home_config.mkdir(parents=True, exist_ok=True)
    return str(home_config)


def _get_default_config_path() -> str:
    """Get the default config file path using a consistent location."""
    config_dir = _get_config_dir()
    return os.path.join(config_dir, 'config.json')


class ConfigManager:
    """
    Manages local configuration storage for Facebook credentials with multi-page support.

    Stores credentials in a secure JSON file (config.json) that:
    - Is created only after first-time setup
    - Can store up to 5 Facebook Pages
    - Provides validation and error handling
    - Supports updating individual pages/credentials
    """

    # Maximum number of pages per license
    MAX_PAGES = 5

    # Sensitive fields that should be masked in logs/debug
    SENSITIVE_FIELDS = ['page_access_token', 'app_secret']

    def __init__(self, config_file: str = None, cookies_file: str = None):
        """
        Initialize the configuration manager.

        Args:
            config_file: Path to config file (optional, defaults to project root config.json)
            cookies_file: Path to cookies file (optional, defaults to cookies.txt in config dir)
        """
        self.config_file = config_file or _get_default_config_path()
        self._cookies_file = cookies_file or os.path.join(os.path.dirname(self.config_file), 'cookies.txt')
        self._config: Dict[str, Any] = {}
        self._pages: List[Dict[str, Any]] = []
        self._loaded = False

    def _get_default_cookies_path(self) -> str:
        """Get the default cookies file path based on config file location."""
        return os.path.join(os.path.dirname(self.config_file), 'cookies.txt')

    def _load(self) -> bool:
        """
        Load configuration from file.
        Handles both new multi-page format and legacy single-page format.
        """
        default_cookies = self._get_default_cookies_path()
        try:
            if not os.path.exists(self.config_file):
                self._config = {'pages': [], 'app_secret': '', 'cookies_file': default_cookies}
                self._loaded = True
                return False

            with open(self.config_file, 'r', encoding='utf-8') as f:
                self._config = json.load(f)

            # Handle legacy single-page format (backward compatibility)
            if 'page_access_token' in self._config and 'pages' not in self._config:
                # Convert legacy format to new multi-page format
                legacy_page = {
                    'page_id': self._config.get('page_id', ''),
                    'page_access_token': self._config.get('page_access_token', ''),
                    'page_name': '',
                    'app_id': self._config.get('app_id', '')
                }
                self._config['pages'] = [legacy_page]
                self._config['app_secret'] = self._config.get('app_secret', '')
                self._config['cookies_file'] = self._config.get('cookies_file', default_cookies)

            # Ensure pages list exists
            if 'pages' not in self._config:
                self._config['pages'] = []

            self._pages = self._config.get('pages', [])
            self._loaded = True
            return True

        except Exception:
            self._config = {'pages': [], 'app_secret': '', 'cookies_file': default_cookies}
            self._pages = []
            self._loaded = True
            return False

    def get_page_count(self) -> int:
        """Get the number of saved pages."""
        if not self._loaded:
            self._load()
        return len(self._pages)

    def is_configured(self) -> bool:
        """
        Check if at least one page is configured.

        Returns:
            True if at least one page exists, False otherwise
        """
        if not self._loaded:
            self._load()
        return len(self._pages) > 0

    def get_pages(self) -> List[Dict[str, Any]]:
        """
        Get all saved pages.

        Returns:
            List of page dictionaries with page_id, page_access_token, page_name, app_id
        """
        if not self._loaded:
            self._load()
        return self._pages.copy()

    def get_page(self, index: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific page by index.

        Args:
            index: Page index (0-based)

        Returns:
            Page dictionary or None if not found
        """
        if not self._loaded:
            self._load()
        if 0 <= index < len(self._pages):
            return self._pages[index].copy()
        return None

    def get_page_by_id(self, page_id: str) -> Optional[Dict[str, Any]]:
        """
        Find a page by its page_id.

        Args:
            page_id: The Facebook Page ID to search for

        Returns:
            Page dictionary or None if not found
        """
        if not self._loaded:
            self._load()
        for page in self._pages:
            if page.get('page_id') == page_id:
                return page.copy()
        return None

    def get_active_page(self) -> Optional[Dict[str, Any]]:
        """
        Get the first (primary) page - for backward compatibility.

        Returns:
            First page dictionary or None if no pages exist
        """
        if not self._loaded:
            self._load()
        if self._pages:
            return self._pages[0].copy()
        return None

    def get_page_access_token(self, page_id: str = None) -> Optional[str]:
        """
        Get the Page Access Token.

        Args:
            page_id: Optional page ID. If None, returns first page's token.

        Returns:
            The access token or None if not found
        """
        if page_id:
            page = self.get_page_by_id(page_id)
            return page.get('page_access_token') if page else None
        page = self.get_active_page()
        return page.get('page_access_token') if page else None

    def get_page_id(self, page_index: int = 0) -> Optional[str]:
        """
        Get a Page ID.

        Args:
            page_index: Page index (0-based, default 0 for first page)

        Returns:
            The page ID or None if not found
        """
        if not self._loaded:
            self._load()
        if 0 <= page_index < len(self._pages):
            return self._pages[page_index].get('page_id')
        return None

    def get_app_id(self, page_id: str = None) -> Optional[str]:
        """
        Get the App ID.

        Args:
            page_id: Optional page ID. If None, returns first page's app_id.

        Returns:
            The App ID or None if not configured
        """
        if page_id:
            page = self.get_page_by_id(page_id)
            return page.get('app_id') if page else None
        page = self.get_active_page()
        return page.get('app_id') if page else None

    def get_app_secret(self) -> Optional[str]:
        """
        Get the Facebook App Secret.

        Returns:
            The App Secret or None if not configured
        """
        if not self._loaded:
            self._load()
        return self._config.get('app_secret')

    def get_cookies_file(self) -> str:
        """
        Get the cookies file path for YouTube authentication.

        Returns:
            Path to cookies.txt file
        """
        if not self._loaded:
            self._load()
        return self._config.get('cookies_file', self._get_default_cookies_path())

    def get_configured_at(self) -> Optional[str]:
        """
        Get the timestamp when configuration was last updated.

        Returns:
            ISO format timestamp string or None
        """
        if not self._loaded:
            self._load()
        return self._config.get('configured_at')

    def add_page(self, page_access_token: str, page_id: str,
                 page_name: str = None, app_id: str = None) -> bool:
        """
        Add a new Facebook Page to the configuration.

        Args:
            page_access_token: Facebook Page Access Token
            page_id: Facebook Page ID
            page_name: Optional display name for the page
            app_id: Facebook App ID (optional, uses existing if not provided)

        Returns:
            True if added successfully, False otherwise
        """
        if not page_access_token or not page_id:
            return False

        if not self._loaded:
            self._load()

        if len(self._pages) >= self.MAX_PAGES:
            return False

        # Check if page already exists
        if self.get_page_by_id(page_id):
            return False

        # Get app_id from existing page if not provided
        if app_id is None and self._pages:
            app_id = self._pages[0].get('app_id')

        new_page = {
            'page_id': page_id,
            'page_access_token': page_access_token,
            'page_name': page_name or '',
            'app_id': app_id or ''
        }

        self._pages.append(new_page)
        self._config['pages'] = self._pages
        self._config['configured_at'] = datetime.now().isoformat()

        return self._save_config()

    def update_page(self, page_index: int, page_access_token: str = None,
                    page_id: str = None, page_name: str = None, app_id: str = None) -> bool:
        """
        Update a specific page's credentials.

        Args:
            page_index: Page index to update
            page_access_token: New access token (None to keep current)
            page_id: New page ID (None to keep current)
            page_name: New page name (None to keep current)
            app_id: New app ID (None to keep current)

        Returns:
            True if updated successfully, False otherwise
        """
        if not self._loaded:
            self._load()

        if page_index < 0 or page_index >= len(self._pages):
            return False

        page = self._pages[page_index]
        if page_access_token is not None:
            page['page_access_token'] = page_access_token
        if page_id is not None:
            page['page_id'] = page_id
        if page_name is not None:
            page['page_name'] = page_name
        if app_id is not None:
            page['app_id'] = app_id

        self._config['configured_at'] = datetime.now().isoformat()
        return self._save_config()

    def update_credential(self, field: str, value: str, page_index: int = 0) -> bool:
        """
        Update a specific field for a page.

        Args:
            field: Field to update (page_access_token, page_id)
            value: New value
            page_index: Page index (default 0)

        Returns:
            True if updated successfully
        """
        return self.update_page(page_index, page_access_token=value if field == 'page_access_token' else None,
                                  page_id=value if field == 'page_id' else None)

    def remove_page(self, page_index: int) -> bool:
        """
        Remove a page from the configuration.

        Args:
            page_index: Page index to remove

        Returns:
            True if removed successfully
        """
        if not self._loaded:
            self._load()

        if page_index < 0 or page_index >= len(self._pages):
            return False

        self._pages.pop(page_index)
        self._config['pages'] = self._pages
        self._config['configured_at'] = datetime.now().isoformat()

        return self._save_config()

    def set_app_secret(self, app_secret: str) -> bool:
        """Set the App Secret."""
        if not self._loaded:
            self._load()

        self._config['app_secret'] = app_secret or ''
        return self._save_config()

    def set_cookies_file(self, cookies_file: str) -> bool:
        """Set the cookies file path."""
        if not self._loaded:
            self._load()

        self._config['cookies_file'] = cookies_file or self._get_default_cookies_path()
        return self._save_config()

    def get_all_credentials(self) -> Dict[str, Any]:
        """
        Get all stored credentials as a dictionary.

        Returns:
            Dictionary of all credential values
        """
        if not self._loaded:
            self._load()
        return {
            'pages': [p.copy() for p in self._pages],
            'app_secret': self._config.get('app_secret', ''),
            'cookies_file': self._config.get('cookies_file', self._get_default_cookies_path()),
            'configured_at': self._config.get('configured_at')
        }

    def get_safe_credentials(self, page_index: int = 0) -> Dict[str, Any]:
        """
        Get credentials with sensitive fields masked.

        Args:
            page_index: Page index for masking

        Returns:
            Dictionary with masked sensitive values
        """
        config = self.get_all_credentials()

        def mask_token(token: str) -> str:
            if not token:
                return '***'
            if len(token) <= 8:
                return '***'
            return '***' + token[-8:]

        for page in config['pages']:
            if 'page_access_token' in page and page['page_access_token']:
                page['page_access_token'] = mask_token(page['page_access_token'])

        if config.get('app_secret'):
            config['app_secret'] = mask_token(config['app_secret'])

        return config

    def _save_config(self) -> bool:
        """
        Save configuration to file.

        Returns:
            True if saved successfully
        """
        try:
            temp_file = f"{self.config_file}.tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)

            os.replace(temp_file, self.config_file)
            return True

        except Exception:
            if os.path.exists(f"{self.config_file}.tmp"):
                try:
                    os.remove(f"{self.config_file}.tmp")
                except:
                    pass
            return False

    def save_credentials(self, page_access_token: str, page_id: str,
                         page_name: str = None, app_id: str = None,
                         app_secret: str = None, cookies_file: str = None) -> bool:
        """
        Save credentials to the configuration file (backward compatible).
        Creates or updates the first page.

        Args:
            page_access_token: Facebook Page Access Token
            page_id: Facebook Page ID
            page_name: Optional display name
            app_id: Facebook App ID (optional)
            app_secret: Facebook App Secret (optional)
            cookies_file: Path to cookies.txt file (optional)

        Returns:
            True if saved successfully, False otherwise
        """
        if not self._loaded:
            self._load()

        if self._pages:
            # Update first page
            self.update_page(0, page_access_token, page_id, page_name, app_id)
        else:
            # Add new page
            self.add_page(page_access_token, page_id, page_name, app_id)

        # Update global settings
        if app_secret is not None:
            self.set_app_secret(app_secret)
        if cookies_file is not None:
            self.set_cookies_file(cookies_file)

        return True

    def clear_credentials(self) -> bool:
        """Clear all saved credentials."""
        try:
            if os.path.exists(self.config_file):
                os.remove(self.config_file)
            self._config = {'pages': [], 'app_secret': '', 'cookies_file': self._get_default_cookies_path()}
            self._pages = []
            self._loaded = True
            return True
        except Exception:
            return False

    def reset_credentials(self) -> bool:
        """Reset all credentials (alias for clear_credentials)."""
        return self.clear_credentials()

    def get_config(self) -> Dict[str, Any]:
        """Get all configuration values."""
        if not self._loaded:
            self._load()
        return self._config.copy()

    def migrate_from_env(self) -> bool:
        """
        Migrate credentials from .env file to config.json if needed.

        Returns:
            True if migration was done or not needed, False on error
        """
        try:
            # Check if config.json already exists
            if os.path.exists(self.config_file):
                self._load()
                return True

            # Try to read from .env
            env_file = '.env'
            if not os.path.exists(env_file):
                return True

            config_values = {}
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('#') or '=' not in line or not line:
                        continue
                    key, _, value = line.partition('=')
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    config_values[key] = value

            # Save as config.json with new format
            if 'PAGE_ACCESS_TOKEN' in config_values and 'PAGE_ID' in config_values:
                page = {
                    'page_id': config_values.get('PAGE_ID', ''),
                    'page_access_token': config_values.get('PAGE_ACCESS_TOKEN', ''),
                    'page_name': '',
                    'app_id': config_values.get('APP_ID', '') if 'APP_ID' in config_values else ''
                }
                self._config = {
                    'pages': [page],
                    'app_secret': config_values.get('APP_SECRET', ''),
                    'cookies_file': self._get_default_cookies_path(),
                    'configured_at': datetime.now().isoformat()
                }
                self._pages = [page]
                self._loaded = True
                return self._save_config()

            return True

        except Exception:
            return False


def create_config_manager(config_file: str = None) -> ConfigManager:
    """Factory function to create a ConfigManager instance."""
    return ConfigManager(config_file=config_file)


# Global instance for convenience
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get the global ConfigManager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = create_config_manager()
    return _config_manager


def reset_config_manager():
    """Reset the global ConfigManager instance."""
    global _config_manager
    _config_manager = None