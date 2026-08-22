"""
Terminal UI Module
Provides modern, colorful terminal output using rich library.
"""

from src.ui.console import console
from src.ui.prompts import PromptUI
from src.ui.messages import Messages

__all__ = ['console', 'PromptUI', 'Messages']