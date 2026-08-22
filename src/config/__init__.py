"""
Configuration Manager Module
Provides secure local storage for user configuration.
"""

from .manager import ConfigManager, get_config_manager, create_config_manager

__all__ = ['ConfigManager', 'get_config_manager', 'create_config_manager']