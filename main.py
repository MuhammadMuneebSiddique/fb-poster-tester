#!/usr/bin/env python3
"""
Facebook Auto Poster + Content Downloader - Main Application
Automates posting to Facebook Pages using the Graph API with content downloading from Instagram/TikTok.

VERSION 2.3.1 - Interactive First-Time Setup Flow
- No .env dependency - credentials stored locally after first-time setup
- Configuration persists across restarts using absolute path
"""

import os
import sys

# Set UTF-8 encoding for Windows terminal compatibility - MUST be before other imports
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

import signal
import time
import datetime
from pathlib import Path
from datetime import datetime as dt_datetime, time as dt_time
from typing import Optional, Dict, Any, List, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.rule import Rule
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.columns import Columns
from rich.style import Style
import random


# ============================================
# Hashtag Utility for Facebook Reels
# ============================================

# List of USA-focused, high-reach hashtags for Facebook Reels (2026)
# Mix of broad reach, viral, community, and niche hashtags
HASHTAG_POOL = [
    # Platform tags
    "#fbreels", "#facebookreels", "#reels", "#trending", "#viral", "#explore",
    "#reelsoffacebook", "#shorts", "#reelsdaily", "#reelsdaily",

    # USA/Focus
    "#americanlife", "#usa", "#usstreets", "#americavibes", "#smallbusinessusa",
    "#shareaamericanmoments", "#americanmoments", "#proudtobeeastern",

    # Viral/Trending
    "#fyp", "#foryou", "#foryoupage", "#trend", "#trendingnow", "#viralcontent",
    "#viralvideo", "#viralshorts", "#reelsoftheday", "#explorepage", "#trendalert",

    # Humor/Relatable
    "#funny", "#funnyvideos", "#relatable", "#relatablecontent", "#comedy",
    "#comedyreels", "#memes", "#relatablememes", "#everydayreels",

    # Lifestyle/Trends
    "#lifestyle", "#lifestylecontent", "#lifestylevibes", "#modernlife", "#dailyvibes",
    "#happymonday", "#fridayfeels", "#weekendlife", "#trend", "#trends",

    # Niche High-Engagement
    "#dance", "#dancereels", "#music", "#musicreels", "#fitness", "#fitnesstips",
    "#diet", "#healthy", "#beauty", "#beautytips", "#fashion", "#fashionreels",
    "#food", "#foodie", "#travel", "#travelreels",

    # Engagement
    "#like", "#likeifyouagree", "#share", "#shareifyouagree", "#comment",
    "#commentbelow", "#save", "#saves", "#follow", "#followforfollow",
]


def get_reels_hashtags(count: int = 10) -> str:
    """
    Randomly select hashtags for Facebook Reels.

    Args:
        count: Number of hashtags to select (default 10, range 8-12)

    Returns:
        Space-separated string of hashtags, e.g., "#fyp #viral #reels"
    """
    # Ensure count is in valid range
    count = max(8, min(12, count))

    # Randomly select hashtags without replacement
    selected = random.sample(HASHTAG_POOL, min(count, len(HASHTAG_POOL)))

    return " ".join(selected)


def append_hashtags(caption: str, count: int = 10) -> str:
    """
    Append random hashtags to a caption.

    Args:
        caption: Original caption text
        count: Number of hashtags to append (default 10)

    Returns:
        Caption with hashtags appended
    """
    if not caption or not isinstance(caption, str):
        hashtags = get_reels_hashtags(count)
        return hashtags

    hashtags = get_reels_hashtags(count)
    return f"{caption.strip()} {hashtags}"

from src.facebook.client import FacebookClient
from src.facebook.poster import FacebookPoster
from src.content.manager import ContentManager, ContentType
from src.scheduler.manager import SchedulerManager
from src.downloader.manager import VideoDownloader, Platform, DownloadStatus
from src.creator.sync_manager import CreatorSyncManager, CreatorVideo
from src.creator.queue_manager import PostQueue, QueueItem
from src.utils.logger import setup_logging
from src.utils.notifications import NotificationManager
from src.ui.console import console, ICONS
from src.ui.messages import Messages
from src.ui.prompts import PromptUI
from src.ui.setup_prompts import SetupPrompts, mask_token
from src.config.manager import ConfigManager, get_config_manager
import pytz
from apscheduler.triggers.cron import CronTrigger


class AppState(Enum):
    """Application state enumeration."""
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass
class InteractiveJob:
    """Represents a scheduled posting job with video URL (downloaded at execution time)."""
    id: str
    video_url: str  # Store the video URL - will be downloaded when job runs
    scheduled_time: dt_time
    days: List[str] = field(default_factory=lambda: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None
    content_id: Optional[str] = None  # Set after download


class InteractiveMenu:
    """Provides a beautiful interactive main menu."""

    @staticmethod
    def show_menu() -> int:
        """
        Show the beautiful main menu and return the user's selection.

        Returns:
            1 for Profile Sync, 2 for Direct Posting, 3 for In a Day Posting, 4 for Exit
        """
        console.print()

        # Create a beautiful header with multiline text
        header_lines = [
            Text("\n                    FACEBOOK AUTO POSTER", "header"),
            Text("\n                    ", "header"),
        ]

        console.print(Align.center(Text.assemble(*header_lines)))
        console.print()

        # Create stylish separator
        console.print()
        console.print(Align.center(Text("═══════════════════════════════════════════════════════════", "cyan")))
        console.print()

        # Display menu options line by line (not in a box)
        console.print()
        console.print(f"  {ICONS['calendar']}  1. Profile Sync")
        console.print(f"       Sync a content creator's profile (YouTube, Instagram, TikTok)")
        console.print(f"       Automatically queue and schedule for posting")
        console.print()
        console.print(f"  {ICONS['link']}  2. Direct Posting")
        console.print(f"       Instant/one-time posting - download and post immediately")
        console.print()
        console.print(f"  {ICONS['clock']}  3. In a Day Posting")
        console.print(f"       Schedule posts for today only (next 24 hours - auto-exits)")
        console.print()
        console.print(f"  {ICONS['key']}  4. Update Credentials")
        console.print(f"       Update your Page Access Token, Page ID, or other settings")
        console.print()
        console.print(f"  {ICONS['x']}  5. Exit")
        console.print(f"       Close the program gracefully")
        console.print()

        # Create a nice separator
        console.print(Align.center(Text("═" * 70, "dim")))
        console.print()

        # Prompt for selection
        console.print()
        console.print(f"[header]{ICONS['rocket']} Choose an option to continue:[/header]")
        console.print()

        while True:
            try:
                choice = Prompt.ask(
                    f"[cyan]Enter your choice (1-5):[/cyan]",
                    choices=["1", "2", "3", "4", "5"],
                    default="1"
                )
                return int(choice)
            except Exception:
                console.print(f"[warning]{ICONS['warning']} Please enter a valid number (1-5)[/warning]")

    @staticmethod
    def show_goodbye():
        """Show a nice goodbye message."""
        console.print()
        console.print()

        # Create a beautiful goodbye panel with ASCII-safe text
        goodbye_text = Text.assemble(
            ("  THANK YOU FOR USING Facebook Auto Poster!\n\n", "green"),
            ("  Your posts will be processed according to your schedule.\n\n", "cyan"),
            ("  Take care and happy posting!\n", "magenta"),
        )

        console.print(Panel(
            goodbye_text,
            border_style="green",
            expand=False,
            padding=(2, 4),
            title="* See You Again! *",
            title_align="center"
        ))
        console.print()


class FacebookAutoPoster:
    """Main application class for Facebook Auto Poster."""

    def __init__(self):
        """Initialize the Facebook Auto Poster application."""
        self.state = AppState.STARTING
        self.logger = None
        self.notification_manager = None
        self.facebook_client = None
        self.facebook_poster = None
        self.content_manager = None
        self.scheduler_manager = None
        self.video_downloader = None

        # NEW: Creator sync manager
        self.creator_sync_manager = None
        self.posting_queue = None
        self._creator_url = None
        self._is_creator_mode = False
        self._configured_times: List[str] = []

        # Multi-page support
        self._active_page_index = 0

        self.running = False
        self.interactive_jobs: Dict[str, InteractiveJob] = {}  # Store interactive jobs

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, _):
        """Handle shutdown signals gracefully."""
        console.print(f"[info]{ICONS['info']} Received signal {signum}, shutting down...[/info]")
        self.stop()

    def initialize(self, skip_schedule: bool = False) -> bool:
        """Initialize all application components."""
        try:
            # Print banner
            Messages.print_banner()

            # Setup logging first
            self.logger = setup_logging({
                "level": "INFO",
                "file": "logs/facebook_poster.log",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "date_format": "%Y-%m-%d %H:%M:%S",
                "max_size_mb": 10,
                "backup_count": 5
            })

            # Initialize notification manager
            self.notification_manager = NotificationManager({
                "enabled": True,
                "title": "Facebook Auto Poster"
            })

            # Check and setup Facebook credentials (first-time setup if needed)
            if not self._check_and_setup_credentials():
                raise ValueError("Failed to configure Facebook credentials")

            # Initialize video downloader with cookies.txt support for YouTube
            config_mgr = get_config_manager()
            cookies_file = config_mgr.get_cookies_file()

            self.video_downloader = VideoDownloader(
                download_folder="downloads",
                logger=self.logger,
                use_cookies_file=True,
                cookies_file=cookies_file
            )

            # Initialize content manager
            self.content_manager = ContentManager(
                config={
                    "content_folder": "content",
                    "shuffle_content": True,
                    "recycle_content": True,
                    "max_image_size_mb": 50,
                    "max_video_size_mb": 500,
                    "default_text": "Check out our latest update! 🚀",
                    "default_hashtags": "#facebook #socialmedia #automation"
                },
                logger=self.logger
            )

            # Initialize Facebook poster
            self.facebook_poster = FacebookPoster(
                self.facebook_client,
                self.content_manager,
                self.logger,
                {
                    "dry_run": os.environ.get("DRY_RUN", "false").lower() == "true",
                    "max_retries": int(os.environ.get("MAX_RETRY_ATTEMPTS", 3)),
                    "retry_delay": int(os.environ.get("RETRY_DELAY_SECONDS", 60)),
                    "retry_backoff": int(os.environ.get("RETRY_BACKOFF_MULTIPLIER", 2)),
                    "max_retry_delay": int(os.environ.get("MAX_RETRY_DELAY_SECONDS", 3600)),
                    "default_hashtags": os.environ.get("DEFAULT_HASHTAGS", "#facebook #socialmedia #automation"),
                    "default_text": os.environ.get("DEFAULT_TEXT", "Check out our latest update!")
                }
            )

            # Initialize scheduler manager
            self.scheduler_manager = SchedulerManager(
                self.facebook_poster,
                self.content_manager,
                self.logger,
                {
                    "timezone": os.environ.get("SCHEDULER_TIMEZONE", "Asia/Karachi"),
                    "coalesce": os.environ.get("SCHEDULER_COALESCE", "true").lower() == "true",
                    "max_instances": int(os.environ.get("SCHEDULER_MAX_INSTANCES", 1)),
                    "misfire_grace_time": int(os.environ.get("SCHEDULER_MISFIRE_GRACE_TIME", 300))
                }
            )

            # NEW: Initialize creator sync manager
            queue_file = os.environ.get("CREATOR_QUEUE_FILE", "content/creator_queue.json")
            self.creator_sync_manager = CreatorSyncManager(
                queue_file=queue_file,
                logger=self.logger,
                use_cookies_file=True,
                cookies_file=cookies_file
            )
            self.posting_queue = PostQueue(os.environ.get("POSTING_QUEUE_FILE", "content/posting_queue.json"))

            # Setup interactive schedule (prompts user for time+link pairs)
            if not skip_schedule:
                self._setup_interactive_schedule()

            self.state = AppState.RUNNING
            console.print(f"[success]{ICONS['check']} Facebook Auto Poster + Downloader initialized successfully![/success]")
            return True

        except Exception as e:
            console.print(f"[error]{ICONS['x']} Failed to initialize: {e}[/error]")
            if self.logger:
                self.logger.error(f"Failed to initialize: {e}", exc_info=True)
            self.state = AppState.ERROR
            return False

    def _initialize_facebook_client(self, page_id: str = None, access_token: str = None):
        """
        Initialize the Facebook Graph API client.

        Args:
            page_id: Facebook Page ID (if None, reads from config)
            access_token: Facebook Page Access Token (if None, reads from config)
        """
        # Get credentials from parameters or config
        config_mgr = get_config_manager()

        if page_id is None:
            page_id = config_mgr.get_page_id()
        if access_token is None:
            access_token = config_mgr.get_page_access_token()

        if not page_id or not access_token:
            raise ValueError(
                "Facebook Page ID and Access Token are required. "
                "Run first-time setup to configure credentials."
            )

        console.print(f"[info]{ICONS['cog']} Initializing Facebook client for Page ID: {page_id}[/info]")
        self.facebook_client = FacebookClient(
            page_id=page_id,
            access_token=access_token,
            api_version="v21.0",
            timeout=120,
            logger=self.logger
        )

        # Test connection
        if not self.facebook_client.test_connection():
            raise ConnectionError("Failed to connect to Facebook Graph API")

        console.print(f"[success]{ICONS['check']} Facebook Graph API connection successful![/success]")

    def _initialize_facebook_client_for_page(self, page_index: int) -> bool:
        """
        Initialize Facebook client for a specific page index with proper error handling.

        Args:
            page_index: Index of the page to initialize

        Returns:
            True if initialization successful, False otherwise
        """
        config_mgr = get_config_manager()
        page = config_mgr.get_page(page_index)

        if not page:
            self._show_error("Page Not Found",
                            f"No page found at index {page_index}.",
                            ["Select another page", "Back"])
            return False

        page_id = page.get('page_id')
        access_token = page.get('page_access_token')
        page_name = page.get('page_name', 'Unnamed Page')

        if not page_id or not access_token:
            self._show_error("Missing Credentials",
                            f"Page '{page_name}' (ID: {page_id or 'unknown'}) is missing required credentials.",
                            ["Update credentials for this page", "Select another page", "Back"])
            return False

        # Invalidate any existing client for a different page
        if self.facebook_client and self.facebook_client.page_id != page_id:
            self.logger.info(f"Switching from page {self.facebook_client.page_id} to {page_id}")
            self.facebook_client = None
            self.facebook_poster = None

        try:
            console.print(f"[info]{ICONS['cog']} Initializing Facebook client for: {page_name} (ID: {page_id})[/info]")
            self.facebook_client = FacebookClient(
                page_id=page_id,
                access_token=access_token,
                api_version="v21.0",
                timeout=120,
                logger=self.logger
            )

            # Test connection with detailed error handling
            if not self.facebook_client.test_connection():
                return self._handle_api_error(page_name, page_id, "Connection test failed")

            # Recreate FacebookPoster with new client
            self._recreate_facebook_poster()

            self._active_page_index = page_index
            console.print(f"[success]{ICONS['check']} Connected to: {page_name} (ID: {page_id})[/success]")
            return True

        except Exception as e:
            return self._handle_api_error(page_name, page_id, str(e))

    def _handle_api_error(self, page_name: str, page_id: str, error_msg: str) -> bool:
        """
        Handle Facebook API errors with user-friendly messages.

        Args:
            page_name: Display name of the page
            page_id: Facebook Page ID
            error_msg: Raw error message from API

        Returns:
            False (always returns False to indicate failure)
        """
        error_lower = error_msg.lower()

        # Categorize the error
        if any(kw in error_lower for kw in ['expired', 'invalid token', 'access token', '190', 'oauth']):
            self._show_error("Facebook Authentication Failed",
                            f"Page: {page_name}\nPage ID: {page_id}\n\nThe Page Access Token is invalid or has expired.\n\nPlease update the access token for this page and try again.",
                            ["Retry", "Update credentials for this page", "Select another page", "Back"])
        elif any(kw in error_lower for kw in ['page id', 'invalid page', '100', 'does not exist']):
            self._show_error("Invalid Page ID",
                            f"Page: {page_name}\nPage ID: {page_id}\n\nThe configured Page ID could not be used with the selected access token.\n\nPlease verify the Page ID and Page Access Token.",
                            ["Retry", "Update credentials for this page", "Select another page", "Back"])
        elif any(kw in error_lower for kw in ['permission', 'scope', '200', 'unauthorized']):
            self._show_error("Facebook Permission Error",
                            f"Page: {page_name}\nPage ID: {page_id}\n\nThe selected access token does not have the required permissions for this operation.\n\nRequired: pages_manage_posts, pages_read_engagement",
                            ["Retry", "Update credentials for this page", "Select another page", "Back"])
        elif any(kw in error_lower for kw in ['network', 'connection', 'timeout', 'dns', 'unreachable']):
            self._show_error("Network Error",
                            f"Page: {page_name}\nPage ID: {page_id}\n\nUnable to connect to Facebook.\n\nPlease check your internet connection and try again.\n\nTechnical details: {error_msg[:200]}",
                            ["Retry", "Back"])
        else:
            self._show_error("Facebook API Error",
                            f"Page: {page_name}\nPage ID: {page_id}\n\nThe selected page could not be initialized.\n\nFacebook returned:\n{error_msg[:300]}",
                            ["Retry", "Update credentials for this page", "Select another page", "Back"])

        # Log technical details
        self.logger.error(f"Facebook API initialization failed for page_id={page_id}: {error_msg}")
        return False

    def _show_error(self, title: str, message: str, options: list):
        """Display a user-friendly error box with options."""
        console.print()
        console.print(Rule(style="red"))
        console.print(f"[error]{ICONS['x']} {title}[/error]")
        console.print(Rule(style="red"))
        console.print()
        console.print(message)
        console.print()
        console.print("[dim]Options:[/dim]")
        for i, opt in enumerate(options, 1):
            console.print(f"  {i}. {opt}")
        console.print()

    def _recreate_facebook_poster(self):
        """Recreate FacebookPoster with the current facebook_client."""
        if self.facebook_client and self.content_manager:
            self.facebook_poster = FacebookPoster(
                self.facebook_client,
                self.content_manager,
                self.logger,
                {
                    "dry_run": os.environ.get("DRY_RUN", "false").lower() == "true",
                    "max_retries": int(os.environ.get("MAX_RETRY_ATTEMPTS", 3)),
                    "retry_delay": int(os.environ.get("RETRY_DELAY_SECONDS", 60)),
                    "retry_backoff": int(os.environ.get("RETRY_BACKOFF_MULTIPLIER", 2)),
                    "max_retry_delay": int(os.environ.get("MAX_RETRY_DELAY_SECONDS", 3600)),
                    "default_hashtags": os.environ.get("DEFAULT_HASHTAGS", "#facebook #socialmedia #automation"),
                    "default_text": os.environ.get("DEFAULT_TEXT", "Check out our latest update!")
                }
            )

    def _run_first_time_setup(self) -> bool:
        """
        Run the first-time setup flow to collect Facebook credentials.

        This is called when credentials are not yet configured.
        Returns True if setup completed successfully, False otherwise.
        """
        console.print()
        console.print(Rule(style="cyan"))
        console.print(f"[header]{ICONS['key']} FIRST-TIME SETUP REQUIRED[/header]")
        console.print(Rule(style="cyan"))
        console.print()

        console.print("[dim]Before you can use this application, you need to configure your Facebook credentials.[/dim]")
        console.print()

        # Show cookies.txt instructions first
        console.print(f"[dim]{ICONS['key']} YouTube Cookie Setup Required[dim]")
        console.print("[dim]Place your cookies.txt file in the project directory for YouTube downloads.[/dim]")
        console.print("[dim]See COOKIES_GUIDE.md for instructions.[/dim]")
        console.print()

        # Ask if user needs help with credentials
        if SetupPrompts.confirm_setup("", ""):
            SetupPrompts.setup_instructions()
            console.print()

        # Get credentials from user (including optional App ID/Secret)
        token, page_id, app_id, app_secret = SetupPrompts.request_credentials(include_optional=True)

        # Get optional cookies file path
        cookies_file = Prompt.ask(
            "[cyan]Cookies file path (press Enter for default 'cookies.txt')[/cyan]",
            default="cookies.txt"
        )

        # Confirm and save
        if SetupPrompts.confirm_setup(token, page_id, app_id, app_secret, cookies_file):
            config_mgr = get_config_manager()
            if config_mgr.save_credentials(token, page_id, app_id, app_secret, cookies_file):
                SetupPrompts.show_setup_success(page_id)
                return True
            else:
                SetupPrompts.show_setup_error("Failed to save credentials")
                return False

        console.print("[yellow]Setup cancelled.[/yellow]")
        return False

    def _check_and_setup_credentials(self) -> bool:
        """
        Check if credentials are configured, run setup if not.
        Does NOT initialize Facebook client - that happens on-demand per operation.

        Returns:
            True if credentials are ready, False otherwise
        """
        config_mgr = get_config_manager()

        if config_mgr.is_configured():
            # Credentials already configured - just verify they exist
            pages = config_mgr.get_pages()
            console.print(f"[dim]Found {len(pages)} configured page(s)[/dim]")
            return True

        # Need to run first-time setup
        if not self._run_first_time_setup():
            return False

        return True

    def _setup_interactive_schedule(self):
        """
        INTERACTIVE FLOW: Ask for number of posts, then time + link pairs.
        Each pair becomes a separate job that downloads and posts at the scheduled time.
        """
        console.print()
        console.print(Rule(style="cyan"))

        # Ask how many posts
        num_posts = PromptUI.ask_number_of_posts()

        console.print(f"\n[cyan]Enter {num_posts} posting times and video links (YouTube/Instagram/TikTok):[/cyan]")
        console.print("[dim]Each time+link pair will be downloaded and posted at the scheduled time.[/dim]")
        console.print()

        schedule_info = []

        for i in range(num_posts):
            console.print()
            console.print(f"[header]{ICONS['calendar']} Post {i+1} of {num_posts}[/header]")

            # Get time
            scheduled_time = PromptUI.ask_time(i + 1, num_posts)

            # Get video link
            while True:
                url = PromptUI.ask_video_url(i + 1, num_posts)

                # Validate URL
                platform = self.video_downloader.detect_platform(url)
                if platform == Platform.UNKNOWN:
                    if not PromptUI.confirm_unknown_platform(url):
                        continue

                break

            # Store the job
            job_id = f"post_{i+1}"
            job = InteractiveJob(
                id=job_id,
                video_url=url,
                scheduled_time=scheduled_time,
                days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
                enabled=True
            )
            self.interactive_jobs[job_id] = job
            schedule_info.append({"id": job_id, "time": scheduled_time.strftime('%H:%M')})

            # Add to APScheduler
            self._add_interactive_job(job)

        # Show summary
        console.print()
        console.print(Rule(style="cyan"))
        console.print()

        # Create summary table
        table = Table(show_header=False, box=None)
        table.add_column("style", width=10)
        table.add_column("content", width=30)

        for i, info in enumerate(schedule_info, 1):
            table.add_row("", f"[green]{ICONS['check']}[/green] Post {i}: {info['time']} PKT")

        console.print(table)
        console.print(Rule(style="cyan"))
        console.print()

    # ============================================
    # NEW: Interactive Menu Handler Methods
    # ============================================

    def run_profile_sync(self):
        """
        Option 1: Profile Sync
        Sync a content creator's profile and start auto-poster mode.
        """
        console.print()
        console.print(Rule(style="cyan"))
        console.print(f"[header]{ICONS['calendar']} PROFILE SYNC MODE[/header]")
        console.print(Rule(style="cyan"))
        console.print()

        console.print(f"[cyan]Enter the creator's profile URL:[/cyan]")
        console.print(f"[dim]Supported: YouTube (@handle), Instagram (@handle), TikTok (@handle)[/dim]")
        console.print()

        while True:
            creator_url = Prompt.ask(f"[cyan]Creator URL[/cyan]")
            if creator_url and PromptUI._is_valid_url(creator_url):
                break
            console.print(f"[warning]{ICONS['warning']} Please enter a valid URL[/warning]")

        # Ask for scheduled times
        console.print()
        console.print(f"[cyan]{ICONS['clock']} Configure posting times (PKT - Asia/Karachi):[/cyan]")
        console.print(f"[dim]Videos will be posted in chronological order (oldest first).[/dim]")

        num_times = PromptUI.ask_number_of_posts(default=3)
        console.print(f"\n[cyan]Enter {num_times} posting times:[/cyan]")

        scheduled_times = []
        for i in range(num_times):
            t = PromptUI.ask_time(i + 1, num_times)
            scheduled_times.append(t.strftime('%H:%M'))

        # Store scheduled times for use in sync_creator
        self._configured_times = scheduled_times

        console.print()

        # Run in creator mode with the specified times
        if not self._run_creator_mode_fast(creator_url, scheduled_times):
            console.print(f"[error]{ICONS['x']} Failed to setup creator mode[/error]")
            return

        # Keep the main thread running until all videos are posted
        console.print()
        console.print(f"[cyan]{ICONS['cog']} Program is running...[/cyan]")
        console.print(f"[info]{ICONS['info']} Press Ctrl+C to stop at any time.[/info]")
        console.print()

        self.state = AppState.RUNNING
        self.running = True

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received - stopping.")
            self.stop()
        finally:
            # Check if we need to stop due to completion
            if not self.running:
                self.logger.info("Program stopped.")

    def run_direct_posting(self):
        """
        Option 2: Direct Posting
        Instant/one-time posting - ask for content URL and post immediately.
        """
        console.print()
        console.print(Rule(style="cyan"))
        console.print(f"[header]{ICONS['link']} DIRECT POSTING MODE[/header]")
        console.print(Rule(style="cyan"))
        console.print()

        console.print(f"[cyan]{ICONS['rocket']} Direct Posting - Post content immediately[/cyan]")
        console.print(f"[dim]This will download the video and post to Facebook immediately.[/dim]")
        console.print()

        # Get video URLs
        console.print(f"[cyan]Enter video links (YouTube/Instagram/TikTok):[/cyan]")
        console.print("[dim]Separate multiple URLs with spaces or enter them one per line.[/dim]")

        urls_input = Prompt.ask(f"[cyan]Video URLs[/cyan]")
        urls = urls_input.replace(',', ' ').split()

        console.print(f"\n[cyan]{ICONS['package']} Downloading content...[/cyan]")

        # Download content
        content_ids = self.download_now(urls)

        if not content_ids:
            console.print(f"[error]{ICONS['x']} No content was downloaded. Cannot post.[/error]")
            return

        console.print(f"[success]{ICONS['check']} Added {len(content_ids)} item(s) to content manager[/success]")

        # Get which content to post
        if len(content_ids) == 1:
            content_id = content_ids[0]
        else:
            console.print()
            table = Table(show_header=True, header_style="cyan", title=f"{ICONS['video']} Select content to post", border_style="cyan")
            table.add_column("ID", style="cyan", width=10)
            table.add_column("Title", style="green", min_width=40)

            for i, cid in enumerate(content_ids):
                item = self.content_manager.content_items.get(cid)
                title = item.title if item else "Unknown"
                table.add_row(cid, title)

            console.print()
            console.print(table)

            choice = Prompt.ask(f"[cyan]Which one to post? Enter ID or number (1-{len(content_ids)})[/cyan]")

            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(content_ids):
                    content_id = content_ids[idx]
                else:
                    console.print(f"[error]{ICONS['x']} Invalid selection[/error]")
                    return
            else:
                # Find by ID
                if choice in content_ids:
                    content_id = choice
                else:
                    console.print(f"[error]{ICONS['x']} Content ID not found[/error]")
                    return

        # Post the content
        console.print()
        console.print(f"[cyan]{ICONS['link']} Posting to Facebook...[/cyan]")

        success = self.facebook_poster.post_content(content_id)

        if success:
            console.print(f"[success]{ICONS['check']} Content posted successfully![/success]")
            Messages.print_post_success(self.content_manager.content_items.get(content_id).title)
        else:
            console.print(f"[error]{ICONS['x']} Failed to post content[/error]")

    def run_one_day_posting(self):
        """
        Option 3: In a Day Posting
        Schedule posts only for today (next 24 hours).
        After all posts are done, the program exits automatically.
        """
        console.print()
        console.print(Rule(style="cyan"))
        console.print(f"[header]{ICONS['clock']} IN-DAY POSTING MODE[/header]")
        console.print(Rule(style="cyan"))
        console.print()

        console.print(f"[cyan]{ICONS['calendar']} Schedule posts for today[/cyan]")
        console.print(f"[dim]Posts will be scheduled for the next 24 hours then auto-exit when complete.[/dim]")
        console.print()

        # Ask how many posts
        num_posts = PromptUI.ask_number_of_posts(default=1)

        console.print(f"\n[cyan]Enter {num_posts} posting time and video link pairs:[/cyan]")
        console.print("[dim]Each pair will be downloaded and posted at the scheduled time today.[/dim]")
        console.print()

        schedule_info = []

        for i in range(num_posts):
            console.print()
            console.print(f"[header]{ICONS['calendar']} Pair {i+1} of {num_posts}[/header]")

            # Get time (defaults to times within next 24 hours)
            default_time = dt_datetime.now().strftime("%H:%M")
            time_input = Prompt.ask(f"[cyan]Post time today (HH:MM, default: {default_time})[/cyan]", default=default_time)

            try:
                scheduled_time = dt_datetime.strptime(time_input, "%H:%M").time()
            except ValueError:
                console.print(f"[warning]{ICONS['warning']} Invalid time format, using default[/warning]")
                scheduled_time = dt_datetime.now().time()

            # Get video URL
            while True:
                url = Prompt.ask(f"[cyan]Video URL for Post {i+1}[/cyan]")
                if url and PromptUI._is_valid_url(url):
                    platform = self.video_downloader.detect_platform(url)
                    if platform == Platform.UNKNOWN:
                        if not PromptUI.confirm_unknown_platform(url):
                            continue
                    break
                console.print(f"[warning]{ICONS['warning']} Please enter a valid URL[/warning]")

            # Store the job
            job_id = f"one_day_post_{i+1}"

            # Create schedule info
            schedule_info.append({
                "time": scheduled_time.strftime('%H:%M'),
                "url": url
            })

            # Add to interactive jobs with today as the days (only today)
            today_abbr = dt_datetime.now(pytz.timezone("Asia/Karachi")).strftime("%a").lower()[:3]
            job = InteractiveJob(
                id=job_id,
                video_url=url,
                scheduled_time=scheduled_time,
                days=[today_abbr],  # Only today
                enabled=True
            )
            self.interactive_jobs[job_id] = job

            # Add to scheduler
            self._add_interactive_job(job)

            console.print(f"[success]{ICONS['check']} Scheduled for {scheduled_time.strftime('%H:%M')} PKT today[/success]")

        # Show summary
        console.print()
        console.print(Rule(style="green"))

        # Create summary panel
        summary_content = Text.assemble(
            (f"{ICONS['check']} Today's Posts Scheduled\n\n", "green"),
            (f"Posts: {num_posts}\n", "cyan"),
            (f"Duration: ~24 hours\n", "cyan"),
            (f"Auto-exit: When all posts complete\n", "yellow"),
        )

        console.print(Panel(
            summary_content,
            border_style="green",
            expand=False
        ))

        # Add completion check job that runs after 24 hours
        def check_completion_and_exit():
            """Check if all jobs are done and exit."""
            time.sleep(5)  # Brief delay to let jobs complete
            if all(job.last_run is not None for job in self.interactive_jobs.values()):
                self.logger.info("All today's posts completed - auto-exiting")
                self.stop()

        # Schedule exit check
        exit_job = self.scheduler_manager.scheduler.add_job(
            check_completion_and_exit,
            'date',
            run_date=dt_datetime.now(pytz.timezone("Asia/Karachi")) + datetime.timedelta(hours=24),
            id='auto_exit',
            name='Auto Exit Check'
        )

        # Start scheduler
        console.print(f"\n[cyan]{ICONS['cog']} Starting scheduler...[/cyan]")
        self.scheduler_manager.start()

        console.print(f"[green]{ICONS['check']} Scheduler is running! Posts will be made today at scheduled times.[/green]")
        console.print(f"[info]{ICONS['info']} The program will auto-exit when all posts are completed.[/info]")
        console.print(f"[info]{ICONS['info']} Press Ctrl+C to stop early.[/info]")
        console.print()

        # Run the loop
        self.state = AppState.RUNNING
        self.running = True

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received - stopping early.")
            self.stop()

    def run_update_credentials(self):
        """
        Option 4: Update Credentials
        Allow users to update their saved credentials.
        """
        console.print()
        console.print(Rule(style="cyan"))
        console.print(f"[header]{ICONS['key']} UPDATE CREDENTIALS[/header]")
        console.print(Rule(style="cyan"))
        console.print()

        config_mgr = get_config_manager()

        # Show current credentials (masked)
        console.print(f"[header]{ICONS['key']} Current Credentials[/header]")
        console.print()
        SetupPrompts.show_credentials_stored(config_mgr.get_all_credentials())

        # Ask what to update
        while True:
            console.print(f"[cyan]{ICONS['edit']} What would you like to do?[/cyan]")
            console.print()
            console.print("  1. Update Page Access Token")
            console.print("  2. Update Page ID")
            console.print("  3. Update App ID")
            console.print("  4. Update App Secret")
            console.print("  5. Update All Credentials")
            console.print("  6. Change Cookies File Path")
            console.print("  7. Back to Main Menu")
            console.print()

            choice = Prompt.ask(
                "[cyan]Enter your choice (1-7):[/cyan]",
                choices=["1", "2", "3", "4", "5", "6", "7"],
                default="7"
            )

            if choice == "7":
                console.print("[dim]Returning to main menu...[/dim]")
                break

            updated = False

            # Update Page Access Token
            if choice == "1":
                token = SetupPrompts.ask_page_access_token()
                if SetupPrompts.confirm_setup(token, config_mgr.get_page_id() or ""):
                    if config_mgr.update_credential('page_access_token', token):
                        console.print(f"[success]{ICONS['check']} Page Access Token updated successfully![/success]")
                        updated = True
                    else:
                        console.print(f"[error]{ICONS['x']} Failed to update token.[/error]")

            # Update Page ID
            elif choice == "2":
                page_id = SetupPrompts.ask_page_id()
                if SetupPrompts.confirm_setup(config_mgr.get_page_access_token() or "", page_id):
                    if config_mgr.update_credential('page_id', page_id):
                        console.print(f"[success]{ICONS['check']} Page ID updated successfully![/success]")
                        updated = True
                    else:
                        console.print(f"[error]{ICONS['x']} Failed to update Page ID.[/error]")

            # Update App ID
            elif choice == "3":
                app_id = SetupPrompts.ask_app_id()
                if app_id:
                    if config_mgr.update_credential('app_id', app_id):
                        console.print(f"[success]{ICONS['check']} App ID updated successfully![/success]")
                        updated = True
                    else:
                        console.print(f"[error]{ICONS['x']} Failed to update App ID.[/error]")
                else:
                    console.print("[dim]App ID not changed (left blank).[/dim]")

            # Update App Secret
            elif choice == "4":
                app_secret = SetupPrompts.ask_app_secret()
                if app_secret:
                    if config_mgr.update_credential('app_secret', app_secret):
                        console.print(f"[success]{ICONS['check']} App Secret updated successfully![/success]")
                        updated = True
                    else:
                        console.print(f"[error]{ICONS['x']} Failed to update App Secret.[/error]")
                else:
                    console.print("[dim]App Secret not changed (left blank).[/dim]")

            # Update All Credentials (fresh setup)
            elif choice == "5":
                console.print(f"[header]{ICONS['key']} Enter New Credentials[/header]")
                console.print()

                # Get all credentials
                token, page_id, app_id, app_secret = SetupPrompts.request_credentials(include_optional=True)

                # Get cookies file
                cookies_file = Prompt.ask(
                    "[cyan]Cookies file path (press Enter for default 'cookies.txt')[/cyan]",
                    default="cookies.txt"
                )

                if SetupPrompts.confirm_setup(token, page_id, app_id, app_secret, cookies_file):
                    if config_mgr.save_credentials(
                        page_access_token=token,
                        page_id=page_id,
                        app_id=app_id,
                        app_secret=app_secret,
                        cookies_file=cookies_file
                    ):
                        console.print(f"[success]{ICONS['check']} All credentials updated successfully![/success]")
                        updated = True
                    else:
                        console.print(f"[error]{ICONS['x']} Failed to save credentials.[/error]")

            # Change Cookies File Path
            elif choice == "6":
                cookies_file = Prompt.ask(
                    "[cyan]Cookie file path[/cyan]",
                    default=config_mgr.get_cookies_file()
                )
                if config_mgr.update_credential('cookies_file', cookies_file):
                    console.print(f"[success]{ICONS['check']} Cookies file path updated to: {cookies_file}[/success]")
                    updated = True
                else:
                    console.print(f"[error]{ICONS['x']} Failed to update cookies file path.[/error]")

            if updated:
                # Invalidate cached Facebook client so it gets recreated with new credentials
                self.facebook_client = None
                self.facebook_poster = None

                # Refresh the display
                console.print()
                console.print(f"[header]{ICONS['key']} Updated Credentials[/header]")
                console.print()
                SetupPrompts.show_credentials_stored(config_mgr.get_all_credentials())

            console.print()
            if not Confirm.ask("[cyan]Update another credential?[/cyan]", default=True):
                break

    def set_active_page(self, index: int) -> bool:
        """Set the active page index for posting operations.

        Args:
            index: Page index to activate

        Returns:
            True if successful, False if initialization failed
        """
        return self._initialize_facebook_client_for_page(index)

    def run_first_time_setup(self):
        """
        First-time setup - ask for credentials for the first page.
        """
        console.print()
        console.print(Rule(style="cyan"))
        console.print(f"[header]{ICONS['key']} FIRST-TIME SETUP[/header]")
        console.print(Rule(style="cyan"))
        console.print()

        console.print("[dim]Welcome! Let's set up your Facebook credentials.[/dim]")
        console.print()

        # Get credentials from user
        token, page_id, app_id, app_secret = SetupPrompts.request_credentials(include_optional=True)

        # Get page name (optional)
        console.print()
        page_name = Prompt.ask(
            "[cyan]Page Name (optional - for easy identification)[/cyan]",
            default=""
        )
        page_name = page_name.strip() if page_name.strip() else None

        # Get cookies file path
        cookies_file = Prompt.ask(
            "[cyan]Cookies file path (press Enter for default 'cookies.txt')[/cyan]",
            default="cookies.txt"
        )

        # Confirm and save
        if SetupPrompts.confirm_setup(token, page_id, app_id, app_secret, cookies_file):
            config_mgr = get_config_manager()
            if config_mgr.add_page(token, page_id, page_name, app_id):
                if app_secret:
                    config_mgr.set_app_secret(app_secret)
                config_mgr.set_cookies_file(cookies_file)
                SetupPrompts.show_setup_success(page_id, page_name)
                self.set_active_page(0)
            else:
                SetupPrompts.show_setup_error("Failed to save credentials")
        else:
            console.print("[yellow]Setup cancelled.[/yellow]")

    def run_add_page(self):
        """Add a new page to the configuration."""
        console.print()
        console.print(Rule(style="cyan"))
        console.print(f"[header]{ICONS['key']} ADD NEW PAGE[/header]")
        console.print(Rule(style="cyan"))
        console.print()

        config_mgr = get_config_manager()
        page_count = config_mgr.get_page_count()
        max_pages = ConfigManager.MAX_PAGES

        if page_count >= max_pages:
            console.print(f"[warning]{ICONS['warning']} Maximum of {max_pages} pages reached![/warning]")
            console.print("[dim]Please update an existing page or contact support for more pages.[/dim]")
            return

        console.print(f"[dim]You have {page_count}/{max_pages - 1} page slots available.[/dim]")
        console.print()

        # Get credentials
        token, page_id, app_id, app_secret = SetupPrompts.request_credentials(include_optional=True)

        # Get page name
        console.print()
        page_name = Prompt.ask(
            "[cyan]Page Name (optional - for easy identification)[/cyan]",
            default=""
        )
        page_name = page_name.strip() if page_name.strip() else None

        # Confirm
        masked_token = mask_token(token)
        console.print()
        console.print(f"[header]{ICONS['key']} Add Page Summary[/header]")
        console.print()
        console.print(f"  [cyan]Page ID:[/cyan] {page_id}")
        console.print(f"  [cyan]Page Name:[/cyan] {page_name or 'Not set'}")
        console.print(f"  [cyan]Access Token:[/cyan] {masked_token}")
        console.print()

        if Confirm.ask("[cyan]Add this page?[/cyan]", default=True):
            if config_mgr.add_page(token, page_id, page_name, app_id):
                if app_secret:
                    config_mgr.set_app_secret(app_secret)
                console.print(f"[success]{ICONS['check']} Page added successfully![/success]")
                console.print(f"[dim]Added as page {page_count + 1} of {max_pages}[/dim]")
            else:
                console.print(f"[error]{ICONS['x']} Failed to add page.[/error]")
        else:
            console.print("[dim]Page not added.[/dim]")

    def run_update_page(self):
        """Update credentials for an existing page."""
        console.print()
        console.print(Rule(style="cyan"))
        console.print(f"[header]{ICONS['key']} UPDATE PAGE CREDENTIALS[/header]")
        console.print(Rule(style="cyan"))
        console.print()

        config_mgr = get_config_manager()
        pages = config_mgr.get_pages()

        if not pages:
            console.print("[warning]{ICONS['warning']} No pages found.[/warning]")
            return

        # Show pages
        SetupPrompts.show_pages_list(pages)

        # Select page to update
        console.print("  0. Cancel")
        for i, page in enumerate(pages):
            page_name = page.get('page_name', '') or f"Page {i + 1}"
            console.print(f"  {i + 1}. Update {page_name}")

        console.print()

        choice = Prompt.ask(
            "[cyan]Select page to update (0 to cancel)[/cyan]",
            choices=[str(i) for i in range(len(pages) + 1)],
            default="0"
        )

        choice_num = int(choice)
        if choice_num == 0:
            console.print("[dim]Cancelled.[/dim]")
            return

        page_index = choice_num - 1
        page = pages[page_index]

        console.print()
        console.print(f"[header]{ICONS['edit']} Update: {page.get('page_name') or f'Page {page_index + 1}'}[/header]")
        console.print()

        # Get new token
        token = SetupPrompts.ask_page_access_token()

        # Get new page ID
        new_page_id = SetupPrompts.ask_page_id()

        # Get page name
        new_name = Prompt.ask(
            "[cyan]Page Name (press Enter to keep current)[/cyan]",
            default=page.get('page_name', '')
        )
        new_name = new_name.strip() if new_name.strip() else page.get('page_name', '')

        # Confirm
        if SetupPrompts.confirm_setup(token, new_page_id, new_name):
            if config_mgr.update_page(page_index, token, new_page_id, new_name):
                console.print(f"[success]{ICONS['check']} Page updated successfully![/success]")
                # Invalidate cached client if we updated the currently active page
                if self._active_page_index == page_index:
                    self.facebook_client = None
                    self.facebook_poster = None
            else:
                console.print(f"[error]{ICONS['x']} Failed to update page.[/error]")

    def run_delete_page(self):
        """Delete a page from the configuration."""
        console.print()
        console.print(Rule(style="cyan"))
        console.print(f"[header]{ICONS['x']} DELETE PAGE[/header]")
        console.print(Rule(style="cyan"))
        console.print()

        config_mgr = get_config_manager()
        pages = config_mgr.get_pages()

        # Can't delete if only one page
        if len(pages) <= 1:
            console.print("[warning]{ICONS['warning']} Cannot delete the last page. Use 'Update Credentials' to modify it instead.[/warning]")
            return

        # Show pages
        SetupPrompts.show_pages_list(pages)

        # Select page to delete
        console.print("  0. Cancel")
        for i, page in enumerate(pages):
            page_name = page.get('page_name', '') or f"Page {i + 1}"
            console.print(f"  {i + 1}. Delete {page_name}")

        console.print()

        choice = Prompt.ask(
            "[cyan]Select page to delete (0 to cancel)[/cyan]",
            choices=[str(i) for i in range(len(pages) + 1)],
            default="0"
        )

        choice_num = int(choice)
        if choice_num == 0:
            console.print("[dim]Cancelled.[/dim]")
            return

        page_index = choice_num - 1
        page = pages[page_index]
        page_name = page.get('page_name', '') or f"Page {page_index + 1}"

        console.print()
        console.print(f"[warning]Are you sure you want to delete '{page_name}'? This cannot be undone.[/warning]")

        if Confirm.ask("[cyan]Delete this page?[/cyan]", default=False):
            if config_mgr.remove_page(page_index):
                # Update active page index if needed
                if self._active_page_index >= len(pages) - 1:
                    self._active_page_index = max(0, self._active_page_index - 1)

                console.print(f"[success]{ICONS['check']} Page deleted successfully![/success]")
            else:
                console.print(f"[error]{ICONS['x']} Failed to delete page.[/error]")

    def reset_creator_queue(self):
        """Reset the creator queue - all videos become pending."""
        if not self.creator_sync_manager:
            console.print("[error]{ICONS['x']} Creator sync manager not initialized.[/error]")
            return

        self.creator_sync_manager.reset_queue()
        self.posting_queue.reset()
        console.print(f"[success]{ICONS['check']} Queue has been reset.[/success]")

    def sync_creator(self, creator_url: str) -> int:
        """
        Sync a content creator's videos and add them to the posting queue.

        Videos are added in chronological order (oldest first).

        Args:
            creator_url: URL of the creator's channel/profile

        Returns:
            Number of new videos added
        """
        if not self.creator_sync_manager:
            console.print("[error]{ICONS['x']} Creator sync manager not initialized.[/error]")
            return 0

        # Get scheduled times from existing jobs or use default
        scheduled_times = self._get_scheduled_times()
        if not scheduled_times:
            # Ask user for scheduled times
            num_times = PromptUI.ask_number_of_posts(default=1)
            console.print(f"\n[cyan]Enter {num_times} posting times for creator videos:[/cyan]")
            scheduled_times = []
            for i in range(num_times):
                t = PromptUI.ask_time(i + 1, num_times)
                scheduled_times.append(t.strftime('%H:%M'))

        # Sync the creator
        new_count = self.creator_sync_manager.sync_creator(creator_url)

        if new_count == 0:
            console.print(f"[info]{ICONS['info']} No new videos to add from {self.creator_sync_manager.creator_name}[/info]")
            return 0

        # Get all videos sorted by date (oldest first)
        all_videos = self.creator_sync_manager.list_videos()

        # Add to posting queue distributed across scheduled times
        added_items = self.posting_queue.add_multiple_videos(
            videos=[{
                'video_url': v.video_url,
                'title': v.title,
                'upload_date': v.upload_date,
                'timestamp': v.timestamp
            } for v in all_videos if v.status == "pending" or v.status not in ["posted", "failed"]],
            scheduled_times=scheduled_times
        )

        console.print(f"[success]{ICONS['check']} Added {len(added_items)} videos to posting queue[/success]")

        return new_count

    def _get_scheduled_times(self) -> List[str]:
        """Get scheduled times from existing interactive jobs."""
        times = []
        for job in self.interactive_jobs.values():
            times.append(job.scheduled_time.strftime('%H:%M'))
        return sorted(times)

    def list_creator_videos(self, limit: int = 50):
        """List videos from the creator queue."""
        self.creator_sync_manager.print_queue_summary()

    # ============================================
    # NEW: Creator Auto Poster Methods
    # ============================================

    def run_creator_mode(self, creator_url: str) -> bool:
        """
        Run in auto-poster mode for a content creator.

        This mode:
        1. Extracts and queues videos from creator profile
        2. Creates scheduled jobs for each time slot
        3. Starts the scheduler automatically
        4. Runs continuously until all videos are posted
        5. Daily re-syncs to pick up new videos

        Args:
            creator_url: URL of the creator's channel/profile

        Returns:
            True if setup successful, False otherwise
        """
        console.print()
        console.print(Rule(style="cyan"))
        console.print(f"[header]{ICONS['rocket']} CONTENT CREATOR AUTO POSTER SETUP[/header]")
        console.print(Rule(style="cyan"))
        console.print()

        # Ask user for scheduled times
        num_times = PromptUI.ask_number_of_posts(default=3)
        console.print(f"\n[cyan]Enter {num_times} posting times (PKT - Asia/Karachi):[/cyan]")
        console.print("[dim]Videos will be posted in chronological order (oldest first).[/dim]")

        scheduled_times = []
        for i in range(num_times):
            t = PromptUI.ask_time(i + 1, num_times)
            scheduled_times.append(t.strftime('%H:%M'))

        console.print(f"\n[info]{ICONS['info']} Times configured: {', '.join(scheduled_times)} PKT[/info]")

        # Step 1: Sync creator and extract videos
        console.print()
        console.print(f"[cyan]{ICONS['calendar']} Step 1: Syncing videos from creator...[/cyan]")

        new_count = self.creator_sync_manager.sync_creator(creator_url)

        if new_count == 0:
            console.print(f"[warning]{ICONS['warning']} No videos found for {self.creator_sync_manager.creator_name}[/warning]")
            return False

        # Step 2: Add videos to posting queue
        console.print()
        console.print(f"[cyan]{ICONS['calendar']} Step 2: Adding videos to posting queue...[/cyan]")

        all_videos = self.creator_sync_manager.list_videos()
        added_items = self.posting_queue.add_multiple_videos(
            videos=[{
                'video_url': v.video_url,
                'title': v.title,
                'upload_date': v.upload_date,
                'timestamp': v.timestamp
            } for v in all_videos],
            scheduled_times=scheduled_times
        )

        console.print(f"[success]{ICONS['check']} Added {len(added_items)} videos to posting queue[/success]")

        # Step 3: Create scheduled jobs
        console.print()
        console.print(f"[cyan]{ICONS['calendar']} Step 3: Creating scheduled jobs...[/cyan]")

        self._create_creator_jobs(scheduled_times)

        # Step 4: Schedule daily re-sync
        console.print()
        console.print(f"[cyan]{ICONS['calendar']} Step 4: Setting up daily re-sync...[/cyan]")

        self._schedule_daily_resync(creator_url)

        # Step 5: Show startup summary
        console.print()
        console.print(Rule(style="green"))
        console.print()
        console.print(Panel(
            Text.assemble(
                (f"{ICONS['rocket']} Content Creator Auto Poster Started\n", "green"),
                (f"Creator: {self.creator_sync_manager.creator_name}\n", "cyan"),
                (f"Total Videos: {self.posting_queue.get_stats()['total']}\n", "yellow"),
                (f"Posting Times: {', '.join(scheduled_times)} PKT daily\n", "green"),
                (f"Re-sync: Daily at 00:05 PKT", "dim"),
            ),
            border_style="green",
            expand=False
        ))

        # Start scheduler
        console.print(f"[cyan]{ICONS['cog']} Starting scheduler...[/cyan]")
        self.scheduler_manager.start()

        console.print()
        console.print(f"[green]{ICONS['check']} Scheduler is running! Videos will be posted at configured times.[/green]")
        console.print(f"[info]{ICONS['info']} The program will keep running until all videos are posted.[/info]")
        console.print(f"[info]{ICONS['info']} Press Ctrl+C to stop at any time.[/info]")
        console.print()

        # Store creator URL for re-sync
        self._creator_url = creator_url
        self._is_creator_mode = True

        return True

    def _run_creator_mode_fast(self, creator_url: str, scheduled_times: List[str]) -> bool:
        """
        Fast creator mode for menu selection - uses pre-configured times.

        Args:
            creator_url: URL of the creator's channel/profile
            scheduled_times: Pre-configured posting times in HH:MM format

        Returns:
            True if setup successful, False otherwise
        """
        console.print()
        console.print(Rule(style="cyan"))
        console.print(f"[header]{ICONS['rocket']} CONTENT CREATOR AUTO POSTER SETUP[/header]")
        console.print(Rule(style="cyan"))
        console.print()

        console.print(f"[info]{ICONS['info']} Times configured: {', '.join(scheduled_times)} PKT[/info]")

        # Step 1: Sync creator and extract videos
        console.print()
        console.print(f"[cyan]{ICONS['calendar']} Syncing videos from creator...[/cyan]")

        new_count = self.creator_sync_manager.sync_creator(creator_url)

        if new_count == 0:
            console.print(f"[warning]{ICONS['warning']} No videos found for {self.creator_sync_manager.creator_name}[/warning]")
            return False

        # Step 2: Add videos to posting queue
        console.print()
        console.print(f"[cyan]{ICONS['calendar']} Adding videos to posting queue...[/cyan]")

        all_videos = self.creator_sync_manager.list_videos()
        added_items = self.posting_queue.add_multiple_videos(
            videos=[{
                'video_url': v.video_url,
                'title': v.title,
                'upload_date': v.upload_date,
                'timestamp': v.timestamp
            } for v in all_videos],
            scheduled_times=scheduled_times
        )

        console.print(f"[success]{ICONS['check']} Added {len(added_items)} videos to posting queue[/success]")

        # Step 3: Create scheduled jobs
        console.print()
        console.print(f"[cyan]{ICONS['calendar']} Creating scheduled jobs...[/cyan]")

        self._create_creator_jobs(scheduled_times)

        # Step 4: Schedule daily re-sync
        console.print()
        console.print(f"[cyan]{ICONS['calendar']} Setting up daily re-sync...[/cyan]")

        self._schedule_daily_resync(creator_url)

        # Step 5: Show startup summary
        console.print()
        console.print(Rule(style="green"))
        console.print()
        console.print(Panel(
            Text.assemble(
                (f"{ICONS['rocket']} Content Creator Auto Poster Started\n", "green"),
                (f"Creator: {self.creator_sync_manager.creator_name}\n", "cyan"),
                (f"Total Videos: {self.posting_queue.get_stats()['total']}\n", "yellow"),
                (f"Posting Times: {', '.join(scheduled_times)} PKT daily\n", "green"),
                (f"Re-sync: Daily at 00:05 PKT", "dim"),
            ),
            border_style="green",
            expand=False
        ))

        # Start scheduler
        console.print(f"[cyan]{ICONS['cog']} Starting scheduler...[/cyan]")
        self.scheduler_manager.start()

        console.print()
        console.print(f"[green]{ICONS['check']} Scheduler is running! Videos will be posted at configured times.[/green]")
        console.print(f"[info]{ICONS['info']} The program will keep running until all videos are posted.[/info]")
        console.print(f"[info]{ICONS['info']} Press Ctrl+C to stop at any time.[/info]")
        console.print()

        # Store creator URL for re-sync
        self._creator_url = creator_url
        self._is_creator_mode = True

        return True

    def _create_creator_jobs(self, scheduled_times: List[str]):
        """
        Create one APScheduler job per scheduled time slot.
        Each job pulls the next pending video from the queue.

        Args:
            scheduled_times: List of times in HH:MM format
        """
        unique_times = sorted(set(scheduled_times))

        for time_str in unique_times:
            # Parse time
            hour, minute = map(int, time_str.split(':'))

            job_id = f"creator_post_{time_str.replace(':', '_')}"

            # Build cron trigger
            trigger = CronTrigger(
                hour=hour,
                minute=minute,
                timezone=pytz.timezone("Asia/Karachi"),
                day_of_week="mon,tue,wed,thu,fri,sat,sun"
            )

            # Add job to scheduler
            self.scheduler_manager.scheduler.add_job(
                self._execute_creator_job,
                trigger=trigger,
                args=[job_id, time_str],
                id=job_id,
                name=f"Creator Post: {time_str} PKT",
                replace_existing=True
            )

            console.print(f"[green]{ICONS['check']}[/green] Created job '{job_id}' at {time_str} PKT daily")

    def _execute_creator_job(self, job_id: str, scheduled_time: str):
        """
        Execute a creator posting job.

        Gets next pending video from queue, downloads it, and posts to Facebook.

        Args:
            job_id: Job identifier
            scheduled_time: The scheduled time string (HH:MM)
        """
        # Print header
        console.print()
        Messages.print_scheduled_post_header(job_id, "")

        # Get next pending item from queue
        item = self.posting_queue.get_next_pending()

        if not item:
            # Queue is empty
            console.print(f"[info]{ICONS['info']} Queue is empty - all videos have been posted![/info]")
            self._check_completion()
            return

        console.print(f"[cyan]{ICONS['package']} Processing: {item.title}[/cyan]")
        console.print(f"[info]{ICONS['info']} Queue Order: {item.scheduled_order}[/info]")
        console.print(f"[info]{ICONS['info']} Scheduled Time: {item.scheduled_time or scheduled_time} PKT[/info]")

        try:
            # Mark as downloading
            self.posting_queue.mark_as_downloading(item.id)

            # Download video
            console.print(f"\n[cyan]{ICONS['download']} Downloading video...[/cyan]")
            self.logger.info(f"Downloading video for creator job: {item.video_url}")

            downloaded_contents = self.video_downloader.download_multiple([item.video_url])

            if not downloaded_contents:
                Messages.print_download_failed("Could not download video")
                self._handle_download_failure(item)
                return

            content = downloaded_contents[0]

            if content.status == DownloadStatus.FAILED:
                Messages.print_download_failed(content.error_message)
                self._handle_download_failure(item)
                return

            Messages.print_download_complete(content.title, str(content.file_path))

            # Add to content manager
            content_type = ContentType.VIDEO if content.mime_type.startswith('video/') else ContentType.IMAGE

            metadata = {
                'title': content.title,
                'description': content.description or "",
                'source_url': content.original_url,
                'platform': content.platform.value,
                'downloaded_at': content.downloaded_at,
                'duration': content.duration,
                'uploader': content.metadata.get('uploader', ''),
            }

            console.print(f"\n[cyan]{ICONS['cog']} Adding to Content Manager...[/cyan]")

            # Prepare message with hashtags
            base_message = content.description[:500] if content.description else ""
            message_with_hashtags = append_hashtags(base_message, count=10)

            content_item = self.content_manager.add_content(
                file_path=content.file_path,
                content_type=content_type,
                title=content.title,
                message=message_with_hashtags,
                metadata=metadata
            )

            if not content_item:
                Messages.print_no_content_message()
                self._handle_download_failure(item)
                return

            Messages.print_content_added(content_item.id, content.title)

            # Post to Facebook
            console.print()
            Messages.print_posting_started()

            console.print(f"[cyan]{ICONS['link']} Posting to Facebook...[/cyan]")
            success = self.facebook_poster.post_content(content_item.id)

            if success:
                # Mark as posted
                self.posting_queue.mark_as_posted(item.id, content_item.id)

                self.logger.info(f"Successfully posted: {item.title}")
                Messages.print_post_success(content.title)

                # Show queue status
                self._show_queue_status()
            else:
                self._handle_post_failure(item, "Failed to post to Facebook")

        except Exception as e:
            self.logger.error(f"Job {job_id} execution error: {e}", exc_info=True)
            console.print(f"[error]{ICONS['x']} ERROR: {e}[/error]")
            if 'item' in dir() and item and hasattr(item, 'retry_count'):
                self._handle_post_failure(item, str(e))
            else:
                # Item might be None or invalid, log and continue
                self.logger.warning(f"Could not update queue for failed job {job_id}")

    def _handle_download_failure(self, item: 'QueueItem'):
        """Handle a failed download by marking the item for retry or failure."""
        self.posting_queue.mark_as_failed(item.id, "Download failed")
        self._show_queue_status()

    def _handle_post_failure(self, item: 'QueueItem', error: str = ""):
        """Handle a failed post with retry logic."""
        item.retry_count += 1

        if item.retry_count < 3:
            item.status = "pending"  # Will retry
            self.posting_queue._save()
            console.print(f"[warning]{ICONS['warning']} Retry #{item.retry_count} scheduled[/warning]")
        else:
            item.status = "failed"
            self.posting_queue._save()
            console.print(f"[error]{ICONS['x']} Max retries reached. Marking as failed.[/error]")

        self._show_queue_status()

    def _schedule_daily_resync(self, _creator_url: str = None):
        """
        Schedule daily re-sync to pick up new videos from creator profile.

        Runs at 00:05 PKT daily to check for new uploads.

        Args:
            _creator_url: The creator's profile URL (unused, uses manager's stored URL)
        """
        # Get current videos for comparison
        all_videos = self.creator_sync_manager.list_videos()
        existing_urls: Set[str] = {v.video_url for v in all_videos}

        def do_resync():
            """Inner function to perform resync."""
            new_videos = self.creator_sync_manager.resync_new_videos(existing_urls)

            if new_videos > 0:
                # Add new videos to posting queue
                all_times = self._get_scheduled_times()

                if all_times:
                    # Add new videos with time distribution
                    new_video_list = self.creator_sync_manager.list_videos()
                    for i, video in enumerate(new_video_list):
                        if video.video_url not in existing_urls:
                            time_idx = i % len(all_times)
                            scheduled_time = all_times[time_idx]

                            self.posting_queue.add_video(
                                video_url=video.video_url,
                                title=video.title,
                                upload_date=video.upload_date,
                                timestamp=video.timestamp,
                                scheduled_time=scheduled_time
                            )

                    self.logger.info(f"Added {len(new_videos)} new videos from daily re-sync")
                    if len(new_videos) > 0:
                        console.print(f"[success]{ICONS['check']} Added {len(new_videos)} new videos from daily re-sync[/success]")
                        self._show_queue_status()
                else:
                    # No times configured, just add to queue without time
                    console.print(f"[info]{ICONS['info']} Added {len(new_videos)} new videos to queue (no scheduled times)[/info]")

    def _show_queue_status(self):
        """Show current queue status."""
        stats = self.posting_queue.get_stats()
        remaining = stats['pending'] + stats['downloading']

        if remaining > 0:
            console.print(f"[info]{ICONS['info']} Queue Status: {stats['pending']} pending, {stats['posted']} posted, {stats['failed']} failed[/info]")
        else:
            console.print(f"[success]{ICONS['check']} All {stats['total']} videos have been posted![/success]")

    def _check_completion(self):
        """Check if all videos are posted and exit if so."""
        stats = self.posting_queue.get_stats()

        if stats['pending'] == 0 and stats['downloading'] == 0 and stats['total'] > 0:
            total = stats['total']
            posted = stats['posted']
            failed = stats['failed']

            console.print()
            console.print(Rule(style="green"))
            console.print()
            console.print(Panel(
                Text.assemble(
                    (f"{ICONS['check']} All videos processed!\n", "green"),
                    (f"\nTotal: {total}\n", "cyan"),
                    (f"Posted: {posted}\n", "green"),
                    (f"Failed: {failed}\n", "red" if failed > 0 else "green"),
                ),
                border_style="green",
                expand=False
            ))

            Messages.print_completion_message()
            self.logger.info("All videos posted - auto-complete")
            self.stop()

    def _get_scheduled_times(self) -> List[str]:
        """Get scheduled times from existing interactive jobs."""
        times = []
        for job in self.interactive_jobs.values():
            times.append(job.scheduled_time.strftime('%H:%M'))
        return sorted(times)

    def _add_interactive_job(self, job: InteractiveJob):
        """Add an interactive job to the scheduler."""
        # Build cron expression from days
        day_map = {
            "mon": "mon", "tue": "tue", "wed": "wed",
            "thu": "thu", "fri": "fri", "sat": "sat", "sun": "sun"
        }
        cron_days = ",".join(day_map.get(d.lower()[:3], d) for d in job.days)

        # Create CronTrigger with Pakistan timezone
        trigger = CronTrigger(
            day_of_week=cron_days,
            hour=job.scheduled_time.hour,
            minute=job.scheduled_time.minute,
            timezone=pytz.timezone("Asia/Karachi")
        )

        # Add job to scheduler
        aps_job = self.scheduler_manager.scheduler.add_job(
            self._execute_interactive_job,
            trigger=trigger,
            args=[job.id],
            id=job.id,
            name=f"Interactive Post: {job.video_url[:30]}...",
            replace_existing=True
        )

        # Update next_run time
        job.next_run = getattr(aps_job, 'next_run_time', None)
        self.logger.info(f"Added interactive job: {job.id} at {job.scheduled_time} (PKT)")
        console.print(f"[green]{ICONS['check']} Scheduled job '{job.id}' at {job.scheduled_time.strftime('%H:%M')} PKT[/green]")

    def _execute_interactive_job(self, job_id: str):
        """
        Execute an interactive job: download the video from URL and post it.
        This is the NEW flow - download happens at execution time, not beforehand.
        """
        # Print header
        Messages.print_scheduled_post_header(job_id, "")

        # Check if job exists
        if job_id not in self.interactive_jobs:
            self.logger.warning(f"Job not found: {job_id}")
            console.print(f"[warning]{ICONS['warning']} WARNING: Job {job_id} not found![/warning]")
            return

        job = self.interactive_jobs[job_id]
        video_url = job.video_url

        Messages.print_job_info(video_url, job.scheduled_time.strftime('%H:%M'))

        try:
            # Step 1: Download the video
            url_display = video_url[:60] + "..." if len(video_url) > 60 else video_url
            console.print(f"\n[cyan]{ICONS['package']} Downloading video from:[/cyan] [url]{url_display}[/url]")
            self.logger.info(f"Downloading video for job {job_id}: {video_url}")

            # Use progress bar for download
            downloaded_contents = self.video_downloader.download_multiple([video_url])

            if not downloaded_contents:
                Messages.print_download_failed("Could not download video")
                return

            content = downloaded_contents[0]

            if content.status == DownloadStatus.FAILED:
                Messages.print_download_failed(content.error_message)
                self.logger.error(f"Download failed for job {job_id}: {content.error_message}")
                return

            Messages.print_download_complete(content.title, content.file_path)

            # Step 2: Add to content manager
            content_type = ContentType.VIDEO if content.mime_type.startswith('video/') else ContentType.IMAGE

            metadata = {
                'title': content.title,
                'description': content.description or "",
                'source_url': content.original_url,
                'platform': content.platform.value,
                'downloaded_at': content.downloaded_at,
                'duration': content.duration,
                'uploader': content.metadata.get('uploader', ''),
            }

            # Prepare message with hashtags
            base_message = content.description[:500] if content.description else ""
            message_with_hashtags = append_hashtags(base_message, count=10)

            content_item = self.content_manager.add_content(
                file_path=content.file_path,
                content_type=content_type,
                title=content.title,
                message=message_with_hashtags,
                metadata=metadata
            )

            if not content_item:
                Messages.print_no_content_message()
                return

            Messages.print_content_added(content_item.id, content.title)

            # Step 3: Post to Facebook
            console.print()
            Messages.print_posting_started()
            success = self.facebook_poster.post_content(content_item.id)

            job.last_run = datetime.now(pytz.timezone("Asia/Karachi"))

            if success:
                self.logger.info(f"Job {job_id} completed successfully")
                Messages.print_post_success(content.title)
            else:
                self.logger.error(f"Job {job_id} failed to post content")
                Messages.print_post_failure("Check logs for details")

            # Check if all jobs are completed
            if self._all_jobs_completed():
                self._show_completion_message()

        except Exception as e:
            self.logger.error(f"Job {job_id} execution error: {e}", exc_info=True)
            console.print(f"[error]{ICONS['x']} ERROR: {job_id} - {e}[/error]")

    def _all_jobs_completed(self) -> bool:
        """Check if all scheduled jobs have been executed at least once."""
        if not self.interactive_jobs:
            return False
        for job in self.interactive_jobs.values():
            if job.last_run is None:
                return False
        return True

    def _show_completion_message(self):
        """Show completion message and exit cleanly."""
        Messages.print_completion_message()
        self.logger.info("All scheduled jobs completed")
        self.stop()

    def start(self):
        """Start the application."""
        if self.state != AppState.RUNNING:
            self.logger.warning("Application not initialized. Call initialize() first.")
            return

        self.logger.info("Starting Facebook Auto Poster + Downloader...")
        self.running = True

        # Start scheduler
        self.scheduler_manager.start()

        # Send startup notification
        num_posts = len(self.interactive_jobs)
        self.notification_manager.send(
            "Facebook Auto Poster Started",
            f"The application is now running and will post {num_posts} times daily."
        )

        # Print startup message
        Messages.print_startup_message(num_posts)

        self.logger.info("Facebook Auto Poster + Downloader is now running!")

        # Get scheduled times
        post_times = [job.scheduled_time.strftime('%H:%M') for job in self.interactive_jobs.values()]
        self.logger.info(f"Posts scheduled at: {', '.join(post_times)} (Pakistan Timezone - Asia/Karachi)")
        self.logger.info("Press Ctrl+C to stop.")

    def stop(self):
        """Stop the application gracefully."""
        if not self.running:
            return

        console.print()
        Messages.print_shutdown_message()
        self.state = AppState.STOPPING
        self.running = False

        # Stop scheduler
        if self.scheduler_manager:
            self.scheduler_manager.stop()

        # Send shutdown notification
        if self.notification_manager:
            self.notification_manager.send(
                "Facebook Auto Poster Stopped",
                "The application has been stopped."
            )

        self.state = AppState.STOPPED
        self.logger.info("Facebook Auto Poster + Downloader stopped.")

    def run(self):
        """Run the application main loop."""
        self.start()

        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received.")
        finally:
            self.stop()

    def post_now(self, content_id: str) -> bool:
        """Post content immediately."""
        if not self.facebook_poster:
            self.logger.error("Poster not initialized")
            return False

        self.logger.info(f"Posting content {content_id} immediately...")
        return self.facebook_poster.post_content(content_id)

    def download_now(self, urls: List[str]) -> List[str]:
        """Download content immediately from provided URLs."""
        if not self.video_downloader:
            self.logger.error("Downloader not initialized")
            return []

        return self._download_and_add_content(urls)

    def _download_and_add_content(self, urls: List[str]) -> List[str]:
        """Download content from URLs and add to content manager."""
        if not urls:
            return []

        self.logger.info(f"Downloading {len(urls)} content items...")
        console.print(f"\n[cyan]{ICONS['package']} Downloading {len(urls)} content items...[/cyan]")

        downloaded_contents = self.video_downloader.download_multiple(urls)
        content_ids = []

        for i, content in enumerate(downloaded_contents):
            if content.status == DownloadStatus.FAILED:
                console.print(f"  [error]{ICONS['x']} Failed: {urls[i]} - {content.error_message}[/error]")
                self.logger.error(f"Download failed for {urls[i]}: {content.error_message}")
                continue

            # Add to content manager
            content_type = ContentType.VIDEO if content.mime_type.startswith('video/') else ContentType.IMAGE

            # Create metadata
            metadata = {
                'title': content.title,
                'description': content.description,
                'source_url': content.original_url,
                'platform': content.platform.value,
                'downloaded_at': content.downloaded_at,
                'duration': content.duration,
                'uploader': content.metadata.get('uploader', ''),
            }

            # Prepare message with hashtags
            base_message = content.description[:500] if content.description else ""
            message_with_hashtags = append_hashtags(base_message, count=10)

            # Add to content manager (copies file to content folder)
            content_item = self.content_manager.add_content(
                file_path=content.file_path,
                content_type=content_type,
                title=content.title,
                message=message_with_hashtags,
                metadata=metadata
            )

            if content_item:
                content_ids.append(content_item.id)
                # Sanitize title for console output (remove emojis)
                safe_title = content.title.encode('ascii', 'ignore').decode('ascii')
                console.print(f"  [green]{ICONS['check']} Added: {safe_title} (ID: {content_item.id})[/green]")
                self.logger.info(f"Added downloaded content: {content_item.id} - {content.title}")
            else:
                console.print(f"  [error]{ICONS['x']} Failed to add to content manager: {content.title}[/error]")

        return content_ids

    def list_jobs(self) -> List[InteractiveJob]:
        """List all scheduled jobs."""
        jobs = list(self.interactive_jobs.values())

        # Update next_run times from scheduler
        for aps_job in self.scheduler_manager.scheduler.get_jobs():
            if aps_job.id in self.interactive_jobs:
                next_run = getattr(aps_job, 'next_run_time', None)
                self.interactive_jobs[aps_job.id].next_run = next_run

        return jobs

    def get_status(self) -> Dict[str, Any]:
        """Get application status."""
        status = {
            "state": self.state.value,
            "running": self.running,
            "jobs_count": len(self.interactive_jobs),
            "content_count": len(self.content_manager.content_items) if self.content_manager else 0,
            "facebook_connected": self.facebook_client is not None and self.facebook_client.test_connection(),
        }

        # Add creator sync status
        if self.creator_sync_manager:
            creator_status = self.creator_sync_manager.get_queue_status()
            status["creator_queue"] = creator_status

        return status


# ============================================
# Helper functions for page selection flow
# ============================================

def _prompt_page_selection(pages: list) -> int | None:
    """
    Prompt user to select a page from the list.

    Args:
        pages: List of page dictionaries

    Returns:
        Selected page index (0-based) or None if cancelled
    """
    from rich.prompt import Prompt

    if not pages:
        console.print("[warning]No pages available to select.[/warning]")
        return None

    if len(pages) == 1:
        # Only one page - auto-select it
        console.print(f"[dim]Auto-selecting the only available page: {pages[0].get('page_name', 'Unnamed')} (ID: {pages[0].get('page_id')})[/dim]")
        return 0

    console.print()
    console.print(f"[cyan]{ICONS['rocket']} Select a page to post on:[/cyan]")
    console.print()

    for i, page in enumerate(pages, 1):
        page_name = page.get('page_name', 'Unnamed Page')
        page_id = page.get('page_id', 'Unknown')
        console.print(f"  {i}. {page_name} (ID: {page_id})")

    console.print()
    console.print("  0. Cancel / Back")
    console.print()

    while True:
        choice = Prompt.ask(
            "[cyan]Enter page number[/cyan]",
            choices=[str(i) for i in range(len(pages) + 1)],
            default=str(len(pages))
        )

        if choice == "0":
            return None

        selected_index = int(choice) - 1
        if 0 <= selected_index < len(pages):
            return selected_index


def _run_page_management_loop():
    """
    Run the Page Management Menu loop.

    This menu handles page management operations and navigation:
    - Select a page to post on
    - Add a new page
    - Update credentials for an existing page
    - Delete a page
    - Exit the application
    """
    while True:
        config_mgr = get_config_manager()
        pages = config_mgr.get_pages()
        page_count = config_mgr.get_page_count()

        console.print()
        console.print(Rule(style="cyan"))
        console.print(f"[header]{ICONS['key']} PAGE MANAGEMENT MENU[/header]")
        console.print(Rule(style="cyan"))
        console.print()

        # Show saved pages
        SetupPrompts.show_pages_list(pages, ConfigManager.MAX_PAGES)

        # Show menu options
        console.print(f"[cyan]What would you like to do?[/cyan]")
        console.print()
        console.print("  1. Select a page to post on")
        console.print("  2. Add a new page")
        if page_count > 1:
            console.print("  3. Update credentials for existing page")
            console.print("  4. Delete a page")
            exit_option = 5
        else:
            exit_option = 4
        console.print(f"  {exit_option}. Exit")
        console.print()

        # Build choices dynamically
        base_choices = ["1", "2"]
        if page_count > 1:
            choices = base_choices + ["3", "4"]
        else:
            choices = base_choices
        choices.append(str(exit_option))

        choice = Prompt.ask(
            "[cyan]Enter your choice[/cyan]",
            choices=choices,
            default="1"
        )

        if choice == "1":
            # Select a page to post on
            selected_index = _prompt_page_selection(pages)
            if selected_index is not None:
                app = FacebookAutoPoster()
                if not app.initialize(skip_schedule=True):
                    console.print(f"[error]{ICONS['x']} Failed to initialize application[/error]")
                    sys.exit(1)
                # Initialize Facebook client for the selected page
                if app._initialize_facebook_client_for_page(selected_index):
                    # Successfully initialized - go to main feature menu
                    _run_main_menu_loop(app)
                # If initialization failed, loop back to page management menu

        elif choice == "2":
            # Add new page - but only if under limit
            if page_count >= ConfigManager.MAX_PAGES:
                console.print(f"[warning]{ICONS['warning']} Maximum of {ConfigManager.MAX_PAGES} pages reached![/warning]")
                console.print("[dim]Contact support for additional pages.[/dim]")
                continue

            app = FacebookAutoPoster()
            if not app.initialize(skip_schedule=True):
                console.print(f"[error]{ICONS['x']} Failed to initialize application[/error]")
                sys.exit(1)
            app.run_add_page()
            # Loop back to show updated page list

        elif choice == "3" and page_count > 1:
            # Update existing page
            app = FacebookAutoPoster()
            if not app.initialize(skip_schedule=True):
                console.print(f"[error]{ICONS['x']} Failed to initialize application[/error]")
                sys.exit(1)
            app.run_update_page()
            # Loop back to show updated page list

        elif choice == "4" and page_count > 1:
            # Delete a page
            app = FacebookAutoPoster()
            if not app.initialize(skip_schedule=True):
                console.print(f"[error]{ICONS['x']} Failed to initialize application[/error]")
                sys.exit(1)
            app.run_delete_page()

            # Check if no pages left after deletion
            config_mgr = get_config_manager()
            if config_mgr.get_page_count() == 0:
                console.print("[yellow]No pages left. Please add a page first.[/yellow]")
                sys.exit(0)
            # Loop back to show updated page list

        elif choice == str(exit_option):
            # Exit
            console.print("[green]Goodbye![/green]")
            sys.exit(0)


def _run_main_menu_loop(app: 'FacebookAutoPoster'):
    """
    Run the main menu loop for the initialized app.

    Args:
        app: Initialized FacebookAutoPoster instance with active Facebook client
    """
    # Show main menu - stays in loop until user explicitly exits
    while True:
        choice = InteractiveMenu.show_menu()

        if choice == 5:
            InteractiveMenu.show_goodbye()
            sys.exit(0)

        if choice == 4:
            # Update Credentials - returns to main menu after
            app.run_update_credentials()
            # Stay in loop after update credentials
            continue

        if choice == 1:
            app.run_profile_sync()
            # Profile sync runs continuously until Ctrl+C, stays in loop
            continue
        elif choice == 2:
            app.run_direct_posting()
            # Direct posting completes - return to main menu
            continue
        elif choice == 3:
            app.run_one_day_posting()
            # One-day posting runs continuously until Ctrl+C, stays in loop
            continue


# ============================================

def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Facebook Auto Poster + Downloader - Automate posting to Facebook Pages with Instagram/TikTok content downloading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                          # Show interactive menu
  python main.py --post-now <id>          # Post content immediately
  python main.py --download <url1> <url2> # Download and add content immediately
  python main.py --list-jobs              # List scheduled jobs
  python main.py --status                 # Show status
  python main.py --test-connection        # Test Facebook API connection
  python main.py --sync-creator <url>     # Sync videos from a creator profile
  python main.py --list-creator-videos    # List videos in the creator queue
  python main.py --reset-creator-queue    # Reset the creator video queue
  python main.py --dry-run                # Test without posting
  python main.py --debug                  # Debug logging
        """
    )

    parser.add_argument(
        "--post-now", "-p",
        type=str,
        help="Post content immediately by content ID"
    )
    parser.add_argument(
        "--download", "-d",
        nargs="+",
        help="Download and add content from URLs immediately"
    )
    parser.add_argument(
        "--list-jobs", "-l",
        action="store_true",
        help="List all scheduled jobs"
    )
    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Show application status"
    )
    parser.add_argument(
        "--test-connection", "-t",
        action="store_true",
        help="Test Facebook API connection"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run in dry-run mode (no actual posts)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    # Page selection option
    parser.add_argument(
        "--page", "-pg",
        type=int,
        help="Select page by index (1-based) for multi-page operations"
    )
    # Credential management options
    parser.add_argument(
        "--update-credentials", "-u",
        action="store_true",
        help="Open credential update wizard"
    )
    # NEW: Creator sync options
    parser.add_argument(
        "--sync-creator",
        type=str,
        metavar="<URL>",
        help="Sync videos from a content creator's profile (YouTube, Instagram, TikTok)"
    )
    parser.add_argument(
        "--list-creator-videos",
        action="store_true",
        help="List videos in the creator queue"
    )
    parser.add_argument(
        "--reset-creator-queue",
        action="store_true",
        help="Reset the creator video queue (mark all as pending)"
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version="Facebook Auto Poster + Downloader 2.3.0"
    )

    args = parser.parse_args()

    # Set debug mode if requested
    if args.debug:
        os.environ["LOG_LEVEL"] = "DEBUG"
    if args.dry_run:
        os.environ["DRY_RUN"] = "true"

    # ============================================
    # Interactive mode - Check configuration and run
    # ============================================
    if len(sys.argv) == 1:
        # Check if we have any pages configured
        config_mgr = get_config_manager()
        page_count = config_mgr.get_page_count()

        if page_count == 0:
            # STATE A: No pages configured - need to run first-time setup
            app = FacebookAutoPoster()
            if not app.initialize(skip_schedule=True):
                console.print(f"[error]{ICONS['x']} Failed to initialize application[/error]")
                sys.exit(1)
            app.run_first_time_setup()

            # Refresh page count after setup to check if page was added
            config_mgr = get_config_manager()
            page_count = config_mgr.get_page_count()

            # If setup was cancelled (still no pages), exit gracefully
            if page_count == 0:
                console.print("[yellow]No pages configured. Setup was cancelled.[/yellow]")
                sys.exit(0)

        # Go to Page Management Menu (works for both STATE A and STATE B)
        _run_page_management_loop()

        # If we reach here, user exited menu without sys.exit - shouldn't happen
        sys.exit(0)

    # CLI commands (only run when arguments are provided)
    app = FacebookAutoPoster()

    # Initialize (skip schedule for non-interactive commands)
    if not app.initialize(skip_schedule=True):
        console.print(f"[error]{ICONS['x']} Failed to initialize application[/error]")
        sys.exit(1)

    # For CLI commands that need Facebook API, select the appropriate page
    if args.page is not None:
        page_index = args.page - 1  # Convert to 0-based
        config_mgr = get_config_manager()
        if not app._initialize_facebook_client_for_page(page_index):
            console.print(f"[error]{ICONS['x']} Failed to initialize Facebook client for page {args.page}[/error]")
            sys.exit(1)
    elif args.test_connection or args.post_now or args.sync_creator or args.update_credentials:
        # These commands need a Facebook client - prompt for page if not specified
        config_mgr = get_config_manager()
        pages = config_mgr.get_pages()
        if len(pages) == 1:
            # Only one page - auto-select
            if not app._initialize_facebook_client_for_page(0):
                sys.exit(1)
        elif len(pages) > 1:
            # Multiple pages - need to specify --page
            console.print(f"[error]{ICONS['x']} Multiple pages configured. Please specify --page <number> (1-{len(pages)})[/error]")
            sys.exit(1)
        else:
            console.print(f"[error]{ICONS['x']} No pages configured. Run interactive mode to add pages.[/error]")
            sys.exit(1)

    # Handle CLI commands
    if args.test_connection:
        if app.facebook_client and app.facebook_client.test_connection():
            Messages.print_connection_test(True, "Connected", app.facebook_client.page_id)
        else:
            Messages.print_connection_test(False)
        return

    if args.post_now:
        success = app.post_now(args.post_now)
        sys.exit(0 if success else 1)

    if args.download:
        content_ids = app.download_now(args.download)
        if content_ids:
            console.print(f"[success]{ICONS['check']} Successfully added {len(content_ids)} items: {content_ids}[/success]")
        else:
            console.print(f"[error]{ICONS['x']} No content was downloaded[/error]")
        return

    if args.list_jobs:
        _list_jobs(app)
        return

    if args.status:
        status = app.get_status()
        Messages.print_status(
            status["state"],
            status["running"],
            status["jobs_count"],
            status["content_count"],
            status["facebook_connected"]
        )
        return

    # NEW: Creator sync commands
    if args.sync_creator:
        # Run in auto-poster mode - sync, setup jobs, and start scheduler
        if app.run_creator_mode(args.sync_creator):
            # Run the scheduler loop
            app.run()
        else:
            console.print(f"[error]{ICONS['x']} Failed to setup creator mode[/error]")
            sys.exit(1)
        return

    if args.list_creator_videos:
        app.list_creator_videos()
        return

    if args.reset_creator_queue:
        app.reset_creator_queue()
        return

    # Handle credential update
    if args.update_credentials:
        app.run_update_credentials()
        return

    # Default: run the scheduler
    app.run()


def _list_jobs(app: FacebookAutoPoster):
    """List all scheduled jobs."""
    jobs = app.list_jobs()

    if not jobs:
        console.print()
        console.print("[info]No scheduled jobs.[/info]")
        return

    # Create table with job info
    table = Table(show_header=True, header_style="cyan", title=f"{ICONS['calendar']} Scheduled Jobs", border_style="cyan")
    table.add_column("Job ID", style="cyan", width=12)
    table.add_column("Time (PKT)", style="green", width=12)
    table.add_column("Video URL", style="blue", min_width=40)
    table.add_column("Status", style="yellow", width=10)
    table.add_column("Last Run", style="dim", width=16)
    table.add_column("Next Run", style="dim", width=16)

    for job in jobs:
        status_text = f"{ICONS['check']} Enabled" if job.enabled else f"{ICONS['x']} Disabled"
        next_run = job.next_run.strftime("%Y-%m-%d %H:%M") if job.next_run else "Never"
        last_run = job.last_run.strftime("%Y-%m-%d %H:%M") if job.last_run else "Never"
        url_short = job.video_url[:40] + "..." if len(job.video_url) > 40 else job.video_url

        table.add_row(
            job.id,
            job.scheduled_time.strftime('%H:%M'),
            url_short,
            status_text,
            last_run,
            next_run
        )

    console.print()
    console.print(table)


if __name__ == "__main__":
    main()