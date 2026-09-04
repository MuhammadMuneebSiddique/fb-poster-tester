"""
TikTok URL Discovery Module

Discovers individual TikTok video URLs from public profiles.
Uses yt-dlp with skip_download=True for metadata discovery only.
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
class TikTokVideoInfo:
    """Represents a TikTok video with metadata."""
    url: str
    video_id: str
    upload_timestamp: Optional[float] = None
    title: str = ""
    author: str = ""
    duration: Optional[int] = None
    thumbnail: str = ""
    view_count: Optional[int] = None
    like_count: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "video_id": self.video_id,
            "upload_timestamp": self.upload_timestamp,
            "title": self.title,
            "author": self.author,
            "duration": self.duration,
            "thumbnail": self.thumbnail,
            "view_count": self.view_count,
            "like_count": self.like_count,
        }


class TikTokDiscovery:
    """
    Discovers TikTok video URLs from public profiles using yt-dlp.

    yt-dlp is used for URL discovery only - actual video downloading
    is handled separately by yt-dlp or ffmpeg when needed.
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger(__name__)

    def normalize_profile_url(self, profile_url: str) -> str:
        """Normalize TikTok profile URL to canonical form."""
        profile_url = profile_url.rstrip('/')

        # Handle @username style URLs
        if '@' in profile_url:
            match = re.search(r'@([a-zA-Z0-9_.]+)', profile_url)
            if match:
                return f"https://www.tiktok.com/@{match.group(1)}"

        return profile_url

    def extract_username(self, profile_url: str) -> str:
        """Extract username from TikTok profile URL."""
        match = re.search(r'@([a-zA-Z0-9_.]+)', profile_url)
        if match:
            return match.group(1)
        return ""

    def discover_video_urls(self, profile_url: str, max_videos: int = 0) -> List[TikTokVideoInfo]:
        """
        Discover all public TikTok video URLs from a profile using yt-dlp.

        Uses yt-dlp with skip_download=True for metadata discovery only.
        Actual video downloading is handled separately.

        Args:
            profile_url: TikTok profile URL (e.g., https://www.tiktok.com/@username)
            max_videos: Maximum number of videos to discover (0 = unlimited, no limit)

        Returns:
            List of TikTokVideoInfo objects with video URLs and metadata
        """
        profile_url = self.normalize_profile_url(profile_url)
        username = self.extract_username(profile_url)

        if not username:
            self.logger.error(f"Could not extract username from URL: {profile_url}")
            console.print(f"[error]{ICONS['x']} Invalid TikTok profile URL: {profile_url}[/error]")
            return []

        video_infos: List[TikTokVideoInfo] = []
        seen_video_ids: Set[str] = set()

        self.logger.info(f"[TIKTOK] Starting discovery for @{username} using yt-dlp discovery")
        console.print(f"\n[cyan]{ICONS['rocket']} Discovering TikTok videos for @{username}[/cyan]")

        import yt_dlp

        try:
            # yt-dlp options for metadata discovery only (no download)
            ydl_opts = {
                'nocheckcertificate': True,
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,  # CRITICAL: Do NOT download, just discover
                'extract_flat': False,
                'ignoreerrors': True,
                'logger': type('Logger', (), {
                    'debug': lambda s, m: None,
                    'info': lambda s, m: None,
                    'warning': lambda s, m: None,
                    'error': lambda s, m: None,
                })(),
                'http_headers': {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'X-TikTok-Language': 'en',
                },
            }

            # yt-dlp extracts the profile page, which contains video entries
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                profile_url_full = f"https://www.tiktok.com/@{username}"
                info = ydl.extract_info(profile_url_full, download=False)

                if not info or 'entries' not in info:
                    self.logger.warning(f"No video entries found in profile {profile_url_full}")
                    console.print(f"[info]{ICONS['info']} No videos found on profile @{username}[/info]")
                    return video_infos

                entries = info['entries']

                for i, entry in enumerate(entries):
                    # Stop if we've reached max_videos
                    if max_videos > 0 and len(video_infos) >= max_videos:
                        self.logger.info(f"Reached max_videos limit of {max_videos}")
                        break

                    if entry is None:
                        continue

                    # Extract video ID
                    video_id = None
                    if entry.get('id'):
                        video_id = str(entry['id'])
                    elif entry.get('video_id'):
                        video_id = str(entry['video_id'])
                    elif entry.get('aweme_id'):
                        video_id = str(entry['aweme_id'])

                    if not video_id:
                        continue

                    # Skip duplicates
                    if video_id in seen_video_ids:
                        continue
                    seen_video_ids.add(video_id)

                    # Extract video URL
                    video_url = None
                    if entry.get('webpage_url'):
                        video_url = entry['webpage_url']
                    elif entry.get('url'):
                        video_url = entry['url']
                    else:
                        video_url = f"https://www.tiktok.com/video/{video_id}"

                    # Extract metadata
                    upload_timestamp = entry.get('timestamp')
                    title = entry.get('title') or ''
                    if isinstance(title, str):
                        title = title[:100]  # Limit title length
                    author = username
                    if entry.get('uploader'):
                        author = entry['uploader']

                    duration = entry.get('duration')
                    thumbnail = ''
                    if entry.get('thumbnails') and isinstance(entry['thumbnails'], list):
                        thumb = entry['thumbnails'][0]
                        if isinstance(thumb, dict) and thumb.get('url'):
                            thumbnail = thumb['url']

                    view_count = entry.get('view_count')
                    like_count = entry.get('like_count')

                    video_info = TikTokVideoInfo(
                        url=video_url,
                        video_id=video_id,
                        upload_timestamp=upload_timestamp,
                        title=title,
                        author=author,
                        duration=duration,
                        thumbnail=thumbnail,
                        view_count=view_count,
                        like_count=like_count,
                    )
                    video_infos.append(video_info)

        except ImportError as e:
            self.logger.error(f"yt-dlp import failed: {e}")
            console.print(f"[error]{ICONS['x']} yt-dlp not installed. Install with: pip install yt-dlp[/error]")
            return []
        except Exception as e:
            self.logger.error(f"TikTok discovery failed: {e}")
            console.print(f"[error]{ICONS['x']} TikTok discovery error: {str(e)[:200]}[/error]")
            return []

        # Sort by upload timestamp (oldest first)
        # Videos with None timestamp go to the end
        video_infos.sort(key=lambda v: v.upload_timestamp or 0)

        console.print(f"[success]{ICONS['check']} Discovered {len(video_infos)} TikTok videos for @{username}[/success]")

        return video_infos

    def validate_video_url(self, video_url: str) -> bool:
        """
        Validate that a TikTok URL points to a valid video.

        Uses yt-dlp to check video availability.
        This is the ONLY place yt-dlp is used for TikTok - for actual video metadata validation.
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