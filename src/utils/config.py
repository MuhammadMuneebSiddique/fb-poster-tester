"""
Configuration Manager
Handles loading, saving, and managing application configuration.
"""

import yaml
import os
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigManager:
    """Manages application configuration from YAML file."""

    def __init__(self, config_path: str = "config.yaml"):
        """
        Initialize the configuration manager.

        Args:
            config_path: Path to configuration file
        """
        self.config_path = Path(config_path)
        self._config: Dict[str, Any] = {}

    def load(self) -> Dict[str, Any]:
        """
        Load configuration from file.

        Returns:
            Configuration dictionary
        """
        # Start with defaults
        self._config = self._get_defaults()

        # Load from YAML if exists
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    file_config = yaml.safe_load(f) or {}
                    self._deep_merge(self._config, file_config)
            except Exception as e:
                print(f"Warning: Failed to load config from {self.config_path}: {e}")

        # Override with environment variables
        self._load_env_overrides()

        return self._config

    def save(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Save configuration to file.

        Args:
            config: Configuration to save (uses current if not provided)

        Returns:
            True if saved successfully
        """
        if config is not None:
            self._config = config

        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self._config, f, default_flow_style=False, sort_keys=False)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by dot-notation key."""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value by dot-notation key."""
        keys = key.split('.')
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def _load_env_overrides(self) -> None:
        """Load configuration overrides from environment variables."""
        # Facebook config
        if os.getenv('PAGE_ACCESS_TOKEN'):
            self._config.setdefault('facebook', {})['access_token'] = os.getenv('PAGE_ACCESS_TOKEN')
        if os.getenv('PAGE_ID'):
            self._config.setdefault('facebook', {})['page_id'] = os.getenv('PAGE_ID')
        if os.getenv('APP_ID'):
            self._config.setdefault('facebook', {})['app_id'] = os.getenv('APP_ID')
        if os.getenv('APP_SECRET'):
            self._config.setdefault('facebook', {})['app_secret'] = os.getenv('APP_SECRET')

        # Scheduling
        if os.getenv('MORNING_TIME'):
            self._config.setdefault('scheduling', {})['morning_time'] = os.getenv('MORNING_TIME')
        if os.getenv('EVENING_TIME'):
            self._config.setdefault('scheduling', {})['evening_time'] = os.getenv('EVENING_TIME')
        if os.getenv('TIMEZONE'):
            self._config.setdefault('scheduling', {})['timezone'] = os.getenv('TIMEZONE')

        # Posting
        if os.getenv('POST_TYPE'):
            self._config.setdefault('posting', {})['post_type'] = os.getenv('POST_TYPE')
        if os.getenv('CONTENT_FOLDER'):
            self._config.setdefault('posting', {})['content_folder'] = os.getenv('CONTENT_FOLDER')

        # Advanced
        if os.getenv('DRY_RUN'):
            self._config.setdefault('advanced', {})['dry_run'] = os.getenv('DRY_RUN').lower() == 'true'
        if os.getenv('DEBUG_MODE'):
            self._config.setdefault('advanced', {})['debug_mode'] = os.getenv('DEBUG_MODE').lower() == 'true'

        # Logging
        if os.getenv('LOG_LEVEL'):
            self._config.setdefault('logging', {})['level'] = os.getenv('LOG_LEVEL')

    def _deep_merge(self, base: Dict[str, Any], override: Dict[str, Any]) -> None:
        """Deep merge two dictionaries."""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _get_defaults(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            'facebook': {
                'page_id': '',
                'access_token': '',
                'app_id': '',
                'app_secret': ''
            },
            'scheduling': {
                'morning_time': '09:00',
                'evening_time': '18:00',
                'timezone': 'UTC',
                'min_hours_between_posts': 6
            },
            'posting': {
                'post_type': 'mixed',
                'content_folder': 'content',
                'shuffle_content': True,
                'recycle_content': True,
                'default_text': 'Check out our latest update! 🚀',
                'default_hashtags': '#facebook #socialmedia #automation'
            },
            'content': {
                'image_extensions': ['jpg', 'jpeg', 'png', 'gif', 'webp'],
                'video_extensions': ['mp4', 'mov', 'avi', 'mkv', 'webm'],
                'max_video_size_mb': 500,
                'max_image_size_mb': 50,
                'default_video_title': 'New Video Post',
                'default_video_description': 'Check out our latest video!'
            },
            'scheduler': {
                'timezone': 'UTC',
                'misfire_grace_time': 300,
                'coalesce': True,
                'max_instances': 1
            },
            'logging': {
                'level': 'INFO',
                'file': 'logs/facebook_poster.log',
                'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                'date_format': '%Y-%m-%d %H:%M:%S',
                'max_size_mb': 10,
                'backup_count': 5
            },
            'retry': {
                'max_attempts': 3,
                'delay_seconds': 60,
                'backoff_multiplier': 2,
                'max_delay_seconds': 3600
            },
            'advanced': {
                'graph_api_version': 'v21.0',
                'request_timeout': 120,
                'dry_run': False,
                'debug_mode': False
            },
            'notifications': {
                'enabled': True,
                'title': 'Facebook Auto Poster'
            },
            'first_run': True,
            'scheduled_jobs': []
        }