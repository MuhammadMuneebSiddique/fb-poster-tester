"""
Rich Console Module
Provides styled console output using the rich library.
"""

from rich.console import Console
from rich.theme import Theme
from rich.style import Style

# Define a professional color scheme
# Cyan for headers/accents, Green for success, Red for errors, Yellow for warnings, Magenta for important info
custom_theme = Theme({
    "header": Style(color="cyan", bold=True),
    "success": Style(color="green", bold=True),
    "error": Style(color="red", bold=True),
    "warning": Style(color="yellow", bold=True),
    "info": Style(color="magenta", bold=False),
    "time": Style(color="cyan", bold=False),
    "url": Style(color="blue", italic=True),
    "job": Style(color="cyan", bold=False),
    "dim": Style(color="white", dim=True),
})

# Create a console instance with our theme
# On Windows, force UTF-8 encoding for proper Unicode support
import os
import sys

# Set environment variable for UTF-8 encoding (must be done before importing rich)
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

# Use force_terminal=True to ensure colors work even when piped
console = Console(theme=custom_theme, legacy_windows=False, force_terminal=True)

# Color constants for direct use
COLORS = {
    "cyan": "#00bfff",
    "green": "#00ff00",
    "red": "#ff0000",
    "yellow": "#ffff00",
    "magenta": "#ff00ff",
    "blue": "#0000ff",
    "white": "#ffffff",
    "dim": "#808080",
}

# Icon constants
ICONS = {
    "check": "✓",
    "x": "✗",
    "warning": "⚠",
    "info": "ℹ",
    "rocket": "🚀",
    "calendar": "📅",
    "video": "🎥",
    "link": "🔗",
    "cog": "⚙",
    "sparkles": "✨",
    "package": "📦",
    "envelope": "📧",
    "bell": "🔔",
    "clock": "🕐",
    "hourglass": "⏳",
    "download": "📥",
    "key": "🔑",
    "edit": "✏",
    "required": "●",
    "page": "📄",
}