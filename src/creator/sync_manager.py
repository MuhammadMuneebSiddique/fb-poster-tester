"""
Creator Sync Manager
Handles extracting video links from creator profiles using yt-dlp.
"""

import os
import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
import hashlib

from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from src.ui.console import console, ICONS


@dataclass
class CreatorVideo:
    """Represents a video from a content creator."""
    video_url: str
    title: str
    upload_date: Optional[str] = None  # YYYYMMDD format from yt-dlp
    timestamp: Optional[float] = None  # Unix timestamp
    uploader: str = ""
    duration: Optional[int] = None
    platform: str = ""  # youtube, instagram, tiktok
    status: str = "pending"  # pending, posted, failed
    posted_at: Optional[str] = None  # ISO timestamp
    content_id: Optional[str] = None  # Generated after download

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "video_url": self.video_url,
            "title": self.title,
            "upload_date": self.upload_date,
            "timestamp": self.timestamp,
            "uploader": self.uploader,
            "duration": self.duration,
            "platform": self.platform,
            "status": self.status,
            "posted_at": self.posted_at,
            "content_id": self.content_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CreatorVideo':
        """Create from dictionary."""
        return cls(
            video_url=data.get("video_url", ""),
            title=data.get("title", ""),
            upload_date=data.get("upload_date"),
            timestamp=data.get("timestamp"),
            uploader=data.get("uploader", ""),
            duration=data.get("duration"),
            platform=data.get("platform", ""),
            status=data.get("status", "pending"),
            posted_at=data.get("posted_at"),
            content_id=data.get("content_id"),
        )


class CreatorSyncManager:
    """
    Manages content creator profile synchronization and video extraction.

    Uses yt-dlp to extract all video links from a creator's profile,
    stores them in chronological order (oldest first), and manages
    the posting queue.
    """

    def __init__(self, queue_file: str = "content/creator_queue.json",
                 logger: Optional[logging.Logger] = None,
                 use_cookies_file: bool = True,
                 cookies_file: str = "cookies.txt"):
        """
        Initialize the Creator Sync Manager.

        Args:
            queue_file: Path to the JSON file storing the video queue
            logger: Logger instance
            use_cookies_file: Whether to use cookies.txt file for YouTube authentication
            cookies_file: Path to cookies.txt file
        """
        self.logger = logger or logging.getLogger(__name__)
        self.queue_file = Path(queue_file)
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)

        # Cookie settings for YouTube authentication
        self.use_cookies_file = use_cookies_file
        self.cookies_file = cookies_file

        # Check if cookies.txt exists for YouTube operations
        if self.use_cookies_file and Path(self.cookies_file).exists():
            self.logger.info(f"Using cookies file: {self.cookies_file} for YouTube extraction")

        # In-memory queue
        self.videos: List[CreatorVideo] = []
        self.creator_url: Optional[str] = None
        self.creator_name: Optional[str] = None

    def detect_platform(self, url: str) -> str:
        """Detect platform from URL."""
        url_lower = url.lower()
        if "youtube.com" in url_lower or "youtu.be" in url_lower or "yt.be" in url_lower:
            return "youtube"
        elif "instagram.com" in url_lower or "instagr.am" in url_lower:
            return "instagram"
        elif "tiktok.com" in url_lower:
            return "tiktok"
        elif "twitter.com" in url_lower or "x.com" in url_lower:
            return "twitter"
        return "unknown"

    def extract_videos(self, creator_url: str) -> List[CreatorVideo]:
        """
        Extract all videos from a creator's profile using yt-dlp.

        Args:
            creator_url: URL of the creator's channel/profile

        Returns:
            List of CreatorVideo objects ordered by upload date (oldest first)
        """
        self.creator_url = creator_url
        self.creator_name = self._extract_creator_name(creator_url)

        platform = self.detect_platform(creator_url)
        if platform == "unknown":
            console.print(f"[error]{ICONS['x']} Unknown platform for URL: {creator_url}[/error]")
            return []

        console.print(f"\n[cyan]{ICONS['rocket']} Extracting videos from {self.creator_name}[/cyan]")
        console.print(f"[dim]Platform: {platform}[/dim]")

        # Normalize YouTube URLs to get full video list
        if platform == "youtube":
            creator_url = self._normalize_youtube_url(creator_url)
            console.print(f"[dim]Normalized URL: {creator_url}[/dim]")

        # Use yt-dlp to extract video information
        videos = self._extract_with_yt_dlp(creator_url, platform)

        # Sort by timestamp (oldest first)
        videos.sort(key=lambda v: (v.timestamp or 0))

        # Update status
        for video in videos:
            video.platform = platform
            video.status = "pending"

        self.videos = videos
        self.logger.info(f"Extracted {len(videos)} videos from {creator_url}")

        return videos

    def _extract_creator_name(self, url: str) -> str:
        """Extract creator name from URL."""
        import re
        # Extract handle from URL patterns like @handle, /handle, or channel name
        # YouTube: @handle or /channel/CHANNEL_ID or /c/name
        if 'youtube.com' in url:
            # Try @handle first
            match = re.search(r'@([a-zA-Z0-9_-]+)', url)
            if match:
                return match.group(1).replace('_', ' ').replace('-', ' ').title()
            # Try /c/ custom URL
            match = re.search(r'/c/([^/]+)', url)
            if match:
                return match.group(1).replace('_', ' ').replace('-', ' ').title()
            # Try channel about page
            match = re.search(r'/channel/([^/]+)', url)
            if match:
                return f"Channel {match.group(1)[:8]}"
            return "YouTube Creator"

        if 'tiktok.com' in url:
            match = re.search(r'@([a-zA-Z0-9_.]+)', url)
            if match:
                return match.group(1)
            return "TikTok Creator"

        if 'instagram.com' in url:
            match = re.search(r'/([^/]+?)(?:$|/)', url.replace('instagram.com', '').lstrip('/'))
            if match and match.group(1) not in ['reels', 'p', 'stories', 'explore']:
                return match.group(1)
            return "Instagram Creator"

        # Generic URL parsing
        match = re.search(r'@?([^/]+?)(?:$|/)', url.rstrip('/'))
        if match:
            name = match.group(1)
            return name.replace('@', '').replace('_', ' ').replace('-', ' ').title()
        return "Content Creator"

    def _normalize_youtube_url(self, url: str) -> str:
        """
        Normalize YouTube URL to ensure full video list is extracted.

        YouTube @username style URLs only show recent videos on the channel page.
        Appending /videos ensures yt-dlp extracts all available videos.
        """
        if "youtube.com" not in url.lower():
            return url

        # Skip if already has /videos
        if "/videos" in url:
            return url

        # Handle @username style URLs - append /videos for full list
        if "@" in url:
            url = url.rstrip("/")
            return f"{url}/videos"

        # Handle channel URLs - append /videos
        if "/channel/" in url or "/c/" in url or "/user/" in url:
            url = url.rstrip("/")
            return f"{url}/videos"

        return url

    def _extract_with_yt_dlp(self, url: str, platform: str) -> List[CreatorVideo]:
        """Use yt-dlp to extract video information."""
        videos = []

        try:
            # Use --flat-playlist for channel/user pages to get video URLs
            # Note: We do NOT limit the number of videos to retrieve all available content
            # YouTube channels typically show most recent uploads when using a channel URL
            # For channels with hundreds of videos, yt-dlp will extract them all
            cmd = [
                "yt-dlp",
                "--dump-json",
                "--no-warnings",
                "--flat-playlist",
            ]

            # Add cookies file for YouTube when enabled to bypass bot detection
            if self.use_cookies_file and ("youtube.com" in url or "youtu.be" in url or "yt.be" in url):
                if Path(self.cookies_file).exists():
                    cmd.extend(["--cookies", self.cookies_file])
                    self.logger.info(f"Using cookies file: {self.cookies_file} for YouTube extraction")
                else:
                    self.logger.warning(f"cookies.txt not found at {self.cookies_file} - YouTube extraction may fail")

            cmd.append(url)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode != 0:
                self.logger.error(f"yt-dlp extraction failed: {result.stderr[:500]}")
                console.print(f"[error]{ICONS['x']} Failed to extract videos: {result.stderr[:200]}[/error]")
                return []

            # Parse flat playlist - each entry is a video
            seen_urls = set()
            for line in result.stdout.strip().split('\n'):
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    # Flat playlist entries have webpage_url
                    video_url = data.get('webpage_url') or data.get('url')
                    if video_url and video_url not in seen_urls:
                        seen_urls.add(video_url)
                        # Create video info from flat data
                        video = self._create_video_from_flat_info(data)
                        if video:
                            videos.append(video)
                except json.JSONDecodeError:
                    continue

            self.logger.info(f"Extracted {len(videos)} video entries from {url}")

        except subprocess.TimeoutExpired:
            self.logger.error("Video extraction timed out")
            console.print(f"[warning]{ICONS['warning']} Extraction timed out[/warning]")
        except Exception as e:
            self.logger.error(f"Error extracting videos: {e}")
            console.print(f"[error]{ICONS['x']} Error extracting videos: {e}[/error]")

        return videos

    def _create_video_from_flat_info(self, data: Dict[str, Any]) -> Optional[CreatorVideo]:
        """Create CreatorVideo from flat playlist entry (limited info)."""
        if 'webpage_url' not in data:
            return None

        # Try to get timestamp from upload_date
        timestamp = None
        upload_date = None
        if 'upload_date' in data:
            # upload_date is in YYYYMMDD format
            upload_date = data['upload_date']
            try:
                dt = datetime.strptime(upload_date, '%Y%m%d')
                timestamp = dt.timestamp()
            except ValueError:
                pass

        return CreatorVideo(
            video_url=data.get('webpage_url', ''),
            title=data.get('title', ''),
            upload_date=upload_date,
            timestamp=timestamp,
            uploader=data.get('uploader', ''),
            duration=data.get('duration'),
            platform=self.detect_platform(data.get('webpage_url', '')),
        )

    def _get_video_info(self, video_url: str) -> Optional[Dict[str, Any]]:
        """Get detailed info for a single video."""
        try:
            cmd = [
                "yt-dlp",
                "--dump-json",
                "--no-warnings",
                "--skip-download"
            ]

            # Add cookies file for YouTube when enabled
            if self.use_cookies_file and ("youtube.com" in video_url or "youtu.be" in video_url or "yt.be" in video_url):
                if Path(self.cookies_file).exists():
                    cmd.extend(["--cookies", self.cookies_file])
                else:
                    self.logger.warning(f"cookies.txt not found at {self.cookies_file}")

            cmd.append(video_url)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                if lines:
                    return json.loads(lines[-1])
        except Exception as e:
            self.logger.warning(f"Could not get info for {video_url}: {e}")

        return None

    def _create_video_from_info(self, data: Dict[str, Any]) -> CreatorVideo:
        """Create CreatorVideo from yt-dlp info dict."""
        # Get timestamp
        timestamp = data.get('timestamp')
        upload_date = None
        if timestamp:
            upload_date = datetime.fromtimestamp(timestamp).strftime('%Y%m%d')

        return CreatorVideo(
            video_url=data.get('webpage_url', data.get('url', '')),
            title=data.get('title', ''),
            upload_date=upload_date,
            timestamp=timestamp,
            uploader=data.get('uploader', ''),
            duration=data.get('duration'),
            platform=data.get('extractor', '').replace('_extractor', '').replace('http:', ''),
        )

    def sync_creator(self, creator_url: str) -> int:
        """
        Sync a creator's content and create a new queue.

        This method extracts all videos from a creator and creates a fresh
        queue sorted chronologically (oldest first).

        Args:
            creator_url: URL of the creator's channel/profile

        Returns:
            Number of videos in the new queue
        """
        # Extract all videos from creator
        all_videos = self.extract_videos(creator_url)

        if not all_videos:
            console.print(f"[warning]{ICONS['warning']} No videos found for {self.creator_name}[/warning]")
            self.videos = []
            self._save_queue()
            return 0

        # Sort by timestamp (oldest first)
        all_videos.sort(key=lambda v: (v.timestamp or 0) or 9999999999)

        # Deduplicate by URL, keeping first occurrence (oldest)
        final_videos = []
        seen_urls = set()

        for video in all_videos:
            if video.video_url not in seen_urls:
                final_videos.append(video)
                seen_urls.add(video.video_url)

        self.videos = final_videos
        self._save_queue()

        total_count = len(final_videos)

        console.print(f"[success]{ICONS['check']} Synced {total_count} videos from {self.creator_name}[/success]")
        console.print(f"[info]{ICONS['info']} Queue updated with chronological order (oldest first)[/info]")

        return total_count

    def resync_new_videos(self, existing_urls: set) -> int:
        """
        Re-sync a creator's profile and add only new videos.

        This method is called daily to check for new uploads and add them
        to the existing queue without duplicating already-queued or posted videos.

        Args:
            existing_urls: Set of video URLs already in the queue

        Returns:
            Number of new videos added
        """
        if not self.creator_url:
            console.print(f"[error]{ICONS['x']} No creator URL set. Call extract_videos() first.[/error]")
            return 0

        console.print(f"\n[cyan]{ICONS['rocket']} Re-syncing {self.creator_name} for new videos...[/cyan]")

        # Extract all videos from creator (with higher limit for re-sync)
        all_videos = self._extract_with_yt_dlp(self.creator_url, self.detect_platform(self.creator_url))

        if not all_videos:
            console.print(f"[info]{ICONS['info']} No videos found during re-sync[/info]")
            return 0

        # Sort by timestamp (oldest first)
        all_videos.sort(key=lambda v: (v.timestamp or 0) or 9999999999)

        # Filter to only new videos
        new_videos = []
        for video in all_videos:
            if video.video_url not in existing_urls:
                video.platform = self.detect_platform(video.video_url)
                video.status = "pending"
                new_videos.append(video)
                self.logger.info(f"New video found: {video.title}")

        if new_videos:
            # Append to existing queue
            self.videos.extend(new_videos)
            self._save_queue()
            console.print(f"[success]{ICONS['check']} Added {len(new_videos)} new videos from {self.creator_name}[/success]")
        else:
            console.print(f"[info]{ICONS['info']} No new videos found during re-sync[/info]")

        return len(new_videos)

    def get_existing_urls(self) -> set:
        """Get set of all video URLs in current queue."""
        return {v.video_url for v in self.videos}

    def _load_queue(self) -> List[CreatorVideo]:
        """Load video queue from JSON file."""
        if not self.queue_file.exists():
            return []

        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            videos = []
            for item in data.get('videos', []):
                videos.append(CreatorVideo.from_dict(item))

            self.creator_name = data.get('creator_name')
            self.creator_url = data.get('creator_url')

            return videos
        except Exception as e:
            self.logger.error(f"Failed to load queue: {e}")
            return []

    def _save_queue(self):
        """Save video queue to JSON file."""
        data = {
            "creator_name": self.creator_name,
            "creator_url": self.creator_url,
            "last_sync": datetime.now().isoformat(),
            "videos": [v.to_dict() for v in self.videos],
            "total_videos": len(self.videos),
            "pending_count": sum(1 for v in self.videos if v.status == "pending"),
            "posted_count": sum(1 for v in self.videos if v.status == "posted"),
            "failed_count": sum(1 for v in self.videos if v.status == "failed"),
        }

        with open(self.queue_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_next_video(self) -> Optional[CreatorVideo]:
        """Get the next pending video in the queue (oldest first)."""
        for video in self.videos:
            if video.status == "pending":
                return video
        return None

    def mark_as_posted(self, video: CreatorVideo, content_id: Optional[str] = None):
        """Mark a video as posted."""
        video.status = "posted"
        video.posted_at = datetime.now().isoformat()
        video.content_id = content_id
        self._save_queue()

    def mark_as_failed(self, video: CreatorVideo, error: str = ""):
        """Mark a video as failed."""
        video.status = "failed"
        self._save_queue()
        self.logger.error(f"Video {video.title} failed: {error}")

    def get_queue_status(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return {
            "total_videos": len(self.videos),
            "pending_count": sum(1 for v in self.videos if v.status == "pending"),
            "posted_count": sum(1 for v in self.videos if v.status == "posted"),
            "failed_count": sum(1 for v in self.videos if v.status == "failed"),
            "next_video": self.get_next_video().title if self.get_next_video() else None,
        }

    def list_videos(self) -> List[CreatorVideo]:
        """List all videos in the queue."""
        return self.videos.copy()

    def clear_queue(self, keep_metadata: bool = True):
        """Clear the video queue."""
        if keep_metadata:
            for video in self.videos:
                video.status = "pending"
                video.posted_at = None
                video.content_id = None
        else:
            self.videos = []
        self._save_queue()

    def reset_queue(self):
        """Reset the queue - all videos become pending."""
        for video in self.videos:
            video.status = "pending"
            video.posted_at = None
            video.content_id = None
        self._save_queue()

    def print_queue_summary(self):
        """Print a summary of the video queue."""
        if not self.videos:
            console.print(f"[info]{ICONS['info']} No videos in queue.[/info]")
            return

        status = self.get_queue_status()

        # Print header
        console.print()
        console.print(Panel(
            Text.assemble(
                (f"{ICONS['calendar']} Creator: {self.creator_name or 'Unknown'}\n", "cyan"),
                (f"URL: {self.creator_url or 'Not set'}\n", "dim"),
                (f"\nTotal Videos: {status['total_videos']}\n", "green"),
                (f"Pending:   {status['pending_count']}  ", "yellow"),
                (f"Posted:    {status['posted_count']}  ", "cyan"),
                (f"Failed:    {status['failed_count']}", "red"),
            ),
            border_style="cyan",
            expand=False
        ))

        # Print video table
        table = Table(show_header=True, header_style="cyan")
        table.add_column("Status", width=8)
        table.add_column("#", width=3)
        table.add_column("Title", min_width=40)
        table.add_column("Date", style="dim", width=12)

        for i, video in enumerate(self.videos, 1):
            status_icon = "✓" if video.status == "posted" else ("✗" if video.status == "failed" else "○")
            status_style = "green" if video.status == "posted" else ("red" if video.status == "failed" else "yellow")
            date_str = video.upload_date or "Unknown"

            table.add_row(
                f"[{status_style}]{status_icon}[/{status_style}]",
                str(i),
                video.title[:60] + "..." if len(video.title) > 60 else video.title,
                date_str
            )

        console.print(table)
        console.print()

    def print_video_details(self, index: int):
        """Print detailed information for a specific video."""
        if index < 1 or index > len(self.videos):
            console.print(f"[error]{ICONS['x']} Invalid video index: {index}[/error]")
            return

        video = self.videos[index - 1]

        console.print()
        console.print(Panel(
            Text.assemble(
                (f"#{index} ", "cyan"),
                (f"{video.title}", "green"),
                (f"\n\nStatus: {ICONS['check'] if video.status == 'posted' else ICONS['circle'] if video.status == 'pending' else ICONS['x']} {video.status.upper()}", "yellow"),
                (f"\nPlatform: {video.platform}", "dim"),
                (f"\nUpload Date: {video.upload_date or 'Unknown'}", "dim"),
                (f"\nDuration: {video.duration // 60}min {video.duration % 60}s" if video.duration else "\nDuration: Unknown", "dim"),
                (f"\nUploader: {video.uploader or 'Unknown'}", "dim"),
                (f"\nURL: {video.video_url}", "blue"),
            ),
            border_style="cyan",
            expand=False
        ))
        console.print()