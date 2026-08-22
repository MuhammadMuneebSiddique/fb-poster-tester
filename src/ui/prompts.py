"""
Rich Prompts Module
Provides styled interactive prompts using rich.prompt.
"""

from rich.prompt import Prompt, Confirm, IntPrompt
from rich.console import Console
from typing import Optional, List
import re
from datetime import time as dt_time

from src.ui.console import console, ICONS


class PromptUI:
    """Provides styled interactive prompts for the application."""

    @staticmethod
    def ask_number_of_posts(default: int = 3) -> int:
        """Prompt user for number of posts to schedule."""
        console.print(f"\n[header]{ICONS['calendar']} POSTING SCHEDULE SETUP[/header]\n")
        console.print(f"[dim]Configure how many posts you want to schedule for Facebook.[/dim]\n")

        while True:
            try:
                num = IntPrompt.ask(
                    f"[cyan]How many posts do you want to schedule?[/cyan]",
                    default=default,
                    show_default=True
                )
                if num < 1:
                    console.print(f"[warning]{ICONS['warning']} Number of posts must be at least 1[/warning]")
                    continue
                if num > 100:
                    console.print(f"[warning]{ICONS['warning']} Maximum 100 posts allowed[/warning]")
                    continue
                return num
            except Exception:
                console.print(f"[error]{ICONS['x']} Invalid number. Please enter a positive integer.[/error]")
                continue

    @staticmethod
    def ask_time(post_num: int, total_posts: int) -> dt_time:
        """Prompt user for a posting time in HH:MM format."""
        console.print(f"\n[header]{ICONS['clock'] if 'clock' in ICONS else '⏰'} Post {post_num} of {total_posts}[/header]")

        while True:
            time_input = Prompt.ask(
                f"[cyan]Enter time {post_num} (HH:MM, 24-hour format, Pakistan Time)[/cyan]",
                default="09:00"
            )

            try:
                scheduled_time = dt_time.fromisoformat(time_input)
                return scheduled_time
            except ValueError:
                console.print(f"[warning]{ICONS['warning']} Invalid time format. Use HH:MM (24-hour format)[/warning]")

    @staticmethod
    def ask_video_url(post_num: int, total_posts: int) -> str:
        """Prompt user for a video URL."""
        console.print(f"\n[cyan]Enter video link {post_num} (YouTube/Instagram/TikTok):[/cyan]")

        while True:
            url = Prompt.ask(
                f"[cyan]Video URL[/cyan]",
                default=""
            )

            if not url:
                console.print(f"[warning]{ICONS['warning']} Video link is required![/warning]")
                continue

            # Validate URL format
            if not PromptUI._is_valid_url(url):
                console.print(f"[warning]{ICONS['warning']} Invalid URL format. Please enter a valid URL.[/warning]")
                continue

            break

        return url

    @staticmethod
    def confirm_unknown_platform(url: str) -> bool:
        """Ask user to confirm if they want to continue with an unknown platform URL."""
        console.print(f"[warning]{ICONS['warning']} Warning: URL may not be from YouTube/Instagram/TikTok.[/warning]")
        return Confirm.ask(
            "[cyan]Continue anyway?[/cyan]",
            default=False
        )

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        """Check if the URL is valid."""
        pattern = re.compile(
            r'^https?://'  # http:// or https://
            r'(www\.)?'  # optional www.
            r'[-a-zA-Z0-9@:%._\+~#=]{1,256}'  # domain
            r'\.[a-zA-Z0-9()]{1,6}'  # TLD
            r'([-a-zA-Z0-9()@:%_\+.~#?&//=]*)$', re.IGNORECASE)
        return pattern.match(url) is not None


# Add clock icon to ICONS if not present
ICONS["clock"] = "🕐"
ICONS["hourglass"] = "⏳"
ICONS["key"] = "🔑"