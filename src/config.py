"""
Configuration Manager Module
Handles loading, saving, and managing application configuration.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import logging


class ConfigManager:
    """Manages application configuration."""

    def __init__(self, config_path: str = "config.yaml"):
        """Initialize the configuration manager."""
        self.config_path = Path(config_path)
        self.logger = logging.getLogger(__name__)

    def load(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            self.logger.warning(f"Config file not found: {self.config_path}")
            return self._get_default_config()

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}
            self.logger.debug(f"Loaded configuration from {self.config_path}")
            return config
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return self._get_default_config()

    def save(self, config: Dict[str, Any]) -> bool:
        """Save configuration to YAML file."""
        try:
            # Create directory if needed
            self.config_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, indent=2)

            self.logger.debug(f"Saved configuration to {self.config_path}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save config: {e}")
            return False

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration."""
        return {
            "first_run": True,
            "facebook": {
                "page_id": "",
                "access_token": ""
            },
            "scheduling": {
                "morning_time": "09:00",
                "evening_time": "18:00",
                "timezone": "UTC",
                "min_hours_between_posts": 6
            },
            "posting": {
                "post_type": "mixed",
                "content_folder": "content",
                "shuffle_content": True,
                "recycle_content": True,
                "default_text": "Check out our latest update! 🚀",
                "default_hashtags": "#facebook #socialmedia #automation"
            },
            "content": {
                "image_extensions": ["jpg", "jpeg", "png", "gif", "webp"],
                "video_extensions": ["mp4", "mov", "avi", "mkv", "webm"],
                "max_video_size_mb": 500,
                "max_image_size_mb": 50,
                "default_video_title": "New Video Post",
                "default_video_description": "Check out our latest video!"
            },
            "scheduler": {
                "timezone": "UTC",
                "misfire_grace_time": 300,
                "coalesce": True,
                "max_instances": 1
            },
            "logging": {
                "level": "INFO",
                "file": "logs/facebook_poster.log",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "date_format": "%Y-%m-%d %H:%M:%S",
                "max_size_mb": 10,
                "backup_count": 5
            },
            "retry": {
                "max_attempts": 3,
                "delay_seconds": 60,
                "backoff_multiplier": 2,
                "max_delay_seconds": 3600
            },
            "advanced": {
                "graph_api_version": "v21.0",
                "request_timeout": 120,
                "dry_run": False,
                "debug_mode": False
            },
            "notifications": {
                "enabled": True,
                "title": "Facebook Auto Poster"
            },
            "scheduled_jobs": []
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key (supports dot notation)."""
        config = self.config_manager.load() if hasattr(self, 'config_manager') else self.load()
        keys = key.split('.')
        value = config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def set(self, key: str, value: Any) -> bool:
        """Set a configuration value by key (supports dot notation)."""
        config = self.load()
        keys = key.split('.')
        current = config

        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]

        current[keys[-1]] = value
        return self.save(config)


def load_env_file(env_path: str = ".env") -> Dict[str, str]:
    """Load environment variables from .env file."""
    env_vars = {}
    path = Path(env_path)

    if not path.exists():
        return env_vars

    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key.strip()] = value.strip()
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to load .env file: {e}")

    return env_vars