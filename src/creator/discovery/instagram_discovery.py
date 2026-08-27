"""
Instagram URL Discovery Module

Discovers individual Instagram Reel/Post video URLs from public profiles using Instaloader.
This module ONLY discovers URLs - it does NOT download videos.
"""

import re
import json
import logging
from typing import List, Optional, Dict, Any, Set
from dataclasses import dataclass

from rich.console import Console
from src.ui.console import console, ICONS


@dataclass
class InstagramMediaInfo:
    """Represents an Instagram Reel/Post with metadata."""
    url: str
    shortcode: str
    upload_timestamp: Optional[float] = None
    title: str = ""
    author: str = ""
    media_type: str = "video"  # video, reel, iar, tv
    thumbnail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "shortcode": self.shortcode,
            "upload_timestamp": self.upload_timestamp,
            "title": self.title,
            "author": self.author,
            "media_type": self.media_type,
            "thumbnail": self.thumbnail,
        }


class InstagramDiscovery:
    """
    Discovers Instagram video URLs from public profiles using Instaloader.

    Uses Instaloader for profile traversal - actual video downloading
    is handled by yt-dlp.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)
        self._instaloader = None

    def _get_instaloader(self):
        """Get or create Instaloader instance."""
        if self._instaloader is None:
            try:
                from instaloader import Instaloader
                self._instaloader = Instaloader(
                    quiet=True,
                    download_geotags=False,
                    download_comments=False,
                    save_metadata=False,
                    compress_json=False,
                )
            except ImportError:
                self.logger.error("Instaloader not installed. Install with: pip install instaloader")
                raise
        return self._instaloader

    def normalize_profile_url(self, profile_url: str) -> str:
        """Normalize Instagram profile URL to canonical form."""
        # Remove trailing slash and query params
        profile_url = profile_url.split('?')[0].rstrip('/')

        # Handle various URL formats
        if '/reels/' in profile_url:
            # Convert /user/reels/ to /user/
            profile_url = profile_url.replace('/reels/', '/')

        if not profile_url.endswith('/') and '/' not in profile_url[11:]:
            profile_url = profile_url + '/'

        return profile_url

    def extract_username(self, profile_url: str) -> str:
        """Extract username from Instagram profile URL."""
        match = re.search(r'instagr\.am/([^/]+)', profile_url)
        if match:
            return match.group(1)
        match = re.search(r'instagram\.com/([^/]+)', profile_url)
        if match:
            return match.group(1)
        return ""

    def discover_video_urls(self, profile_url: str, max_videos: int = 100) -> List[InstagramMediaInfo]:
        """
        Discover all public Instagram video URLs from a profile using Instaloader.

        Args:
            profile_url: Instagram profile URL (e.g., https://www.instagram.com/username/)
            max_videos: Maximum number of videos to discover (0 = unlimited)

        Returns:
            List of InstagramMediaInfo objects with video URLs and metadata
        """
        profile_url = self.normalize_profile_url(profile_url)
        username = self.extract_username(profile_url)

        if not username:
            self.logger.error(f"Could not extract username from URL: {profile_url}")
            console.print(f"[error]{ICONS['x']} Invalid Instagram profile URL: {profile_url}[/error]")
            return []

        video_infos: List[InstagramMediaInfo] = []
        seen_shortcodes: Set[str] = set()

        self.logger.info(f"[INSTAGRAM] Starting discovery for @{username} using Instaloader")
        console.print(f"\n[cyan]{ICONS['rocket']} Discovering Instagram videos for @{username}[/cyan]")

        try:
            # Get Instaloader instance
            loader = self._get_instaloader()

            from instaloader import Profile

            # Load the profile
            try:
                profile = Profile.from_username(loader.context, username)
            except Exception as e:
                self.logger.error(f"Could not load profile @{username}: {e}")
                console.print(f"[error]{ICONS['x']} Could not load Instagram profile: {e}[/error]")
                return []

            # Iterate through profile posts
            post_count = 0
            for post in profile.get_posts():
                post_count += 1

                # Check if this is video media
                if post.is_video:
                    shortcode = post.shortcode
                    if shortcode not in seen_shortcodes:
                        seen_shortcodes.add(shortcode)

                        video_url = f"https://www.instagram.com/reel/{shortcode}/"

                        video_info = InstagramMediaInfo(
                            url=video_url,
                            shortcode=shortcode,
                            upload_timestamp=post.date_utc.timestamp(),
                            title=post.title or post.caption or "",
                            author=username,
                            media_type='reel' if post.tagged_users else 'video',
                            thumbnail=post.url or "",
                        )
                        video_infos.append(video_info)

                        if max_videos > 0 and len(video_infos) >= max_videos:
                            break

            self.logger.info(f"[INSTAGRAM] Iterated {post_count} posts, found {len(video_infos)} videos")

        except ImportError as e:
            self.logger.error(f"Instaloader import failed: {e}")
            console.print(f"[error]{ICONS['x']} Instaloader not installed. Install with: pip install instaloader[/error]")
            return []
        except Exception as e:
            self.logger.error(f"Instaloader discovery failed: {e}")
            console.print(f"[error]{ICONS['x']} Instagram discovery error: {str(e)[:200]}[/error]")
            return []

        # Sort by upload timestamp (oldest first)
        video_infos.sort(key=lambda v: v.upload_timestamp or 0)

        console.print(f"[success]{ICONS['check']} Discovered {len(video_infos)} Instagram videos for @{username}[/success]")

        return video_infos

    def validate_video_url(self, video_url: str) -> bool:
        """
        Validate that an Instagram URL points to a valid video.

        Uses yt-dlp to check video availability.
        This is the ONLY place yt-dlp is used for Instagram - for actual video metadata.
        """
        import subprocess

        try:
            cmd = [
                "yt-dlp",
                "--dump-json",
                "--no-warnings",
                "--skip-download",
                video_url
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0 and result.stdout.strip():
                return True

            return False

        except subprocess.TimeoutExpired:
            self.logger.debug(f"Video URL validation timeout for {video_url}")
            return False
        except Exception as e:
            self.logger.debug(f"Video URL validation failed: {e}")
            return False