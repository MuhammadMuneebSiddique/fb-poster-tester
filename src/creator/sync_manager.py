"""
Creator Sync Manager
Handles extracting video links from creator profiles using yt-dlp.

For TikTok and Instagram profiles, this uses dedicated URL discovery modules
that ONLY discover video URLs. Actual video downloading is handled by yt-dlp.

INTEGRATED: Session persistence with page-scoped isolation via SessionManager.
"""

import os
import json
import logging
import re
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
from src.creator.discovery.tiktok_discovery import TikTokDiscovery, TikTokVideoInfo
from src.creator.discovery.instagram_discovery import InstagramDiscovery, InstagramMediaInfo
from src.creator.session import SessionManager, SessionVideo, VideoStatus, CreatorSession


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
    status: str = "pending"  # pending, downloading, downloaded, posted, failed
    posted_at: Optional[str] = None  # ISO timestamp
    content_id: Optional[str] = None  # Generated after download
    download_attempts: int = 0  # Count of download attempts for retry
    source_video_id: Optional[str] = None  # Source platform video ID (e.g., TikTok aweme ID)

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
            "source_video_id": self.source_video_id,
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
            source_video_id=data.get("source_video_id"),
        )


class CreatorSyncManager:
    """
    Manages content creator profile synchronization and video extraction.

    Uses yt-dlp to extract all video links from a creator's profile,
    stores them in chronological order (oldest first), and manages
    the posting queue.

    INTEGRATED: Session persistence with page-scoped isolation via SessionManager.
    """

    def __init__(self, queue_file: str = "content/creator_queue.json",
                 logger: Optional[logging.Logger] = None,
                 use_cookies_file: bool = True,
                 cookies_file: str = "cookies.txt",
                 page_id: Optional[str] = None):
        """
        Initialize the Creator Sync Manager.

        Args:
            queue_file: Path to the JSON file storing the video queue
            logger: Logger instance
            use_cookies_file: Whether to use cookies.txt file for YouTube authentication
            cookies_file: Path to cookies.txt file
            page_id: Facebook Page ID for page-scoped session management
        """
        self.logger = logger or logging.getLogger(__name__)
        self.queue_file = Path(queue_file)
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)

        # Cookie settings for YouTube authentication
        self.use_cookies_file = use_cookies_file
        self.cookies_file = cookies_file

        # Page ID for session isolation
        self.page_id = page_id

        # Save control - disabled during creator mode (session file is source of truth)
        self._save_enabled = True

        # Check if cookies.txt exists for YouTube operations
        if self.use_cookies_file and Path(self.cookies_file).exists():
            self.logger.info(f"Using cookies file: {self.cookies_file} for YouTube extraction")

        # In-memory queue (legacy support)
        self.videos: List[CreatorVideo] = []
        self.creator_url: Optional[str] = None
        self.creator_name: Optional[str] = None

        # Session manager for page-scoped persistence
        self.session_manager: Optional[SessionManager] = None
        self.current_session: Optional[CreatorSession] = None

        if page_id:
            self.session_manager = SessionManager(page_id=page_id)
            # Check for incomplete session on initialization
            if self.session_manager.has_incomplete_session():
                self.current_session = self.session_manager.get_incomplete_session()
                self.creator_url = self.current_session.creator_url
                self.creator_name = self.current_session.creator_name
                self.logger.info(f"Loaded incomplete session for page {page_id}")

    def disable_save(self, disabled: bool = True):
        """Disable automatic saving to the creator queue file."""
        self._save_enabled = disabled

    def enable_save(self, enabled: bool = True):
        """Enable automatic saving to the creator queue file."""
        self._save_enabled = enabled

    def _should_save(self) -> bool:
        """Check if queue should save to file."""
        return self._save_enabled

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
        Extract all videos from a creator's profile.

        Uses the appropriate method based on platform:
        - YouTube: yt-dlp extraction (unchanged)
        - TikTok: TikTokDiscovery module ONLY for URL discovery
        - Instagram: Instaloader module ONLY for URL discovery

        CRITICAL ARCHITECTURE:
        - Discovery modules discover video URLs ONLY
        - URLs are saved to persistent queue
        - yt-dlp download/posting happens at scheduler time
        - Creator setup succeeds immediately after discovery
        - URLs are NOT discarded due to yt-dlp validation failure

        Args:
            creator_url: URL of the creator's channel/profile

        Returns:
            List of CreatorVideo objects (pending status, ready for scheduler)
        """
        self.creator_url = creator_url
        self.creator_name = self._extract_creator_name(creator_url)

        platform = self.detect_platform(creator_url)
        if platform == "unknown":
            console.print(f"[error]{ICONS['x']} Unknown platform for URL: {creator_url}[/error]")
            return []

        console.print(f"\n[cyan]{ICONS['rocket']} Extracting videos from {self.creator_name}[/cyan]")
        console.print(f"[dim]Platform: {platform}[/dim]")

        # Normalize platform-specific URLs
        if platform == "youtube":
            creator_url = self._normalize_youtube_url(creator_url)
            console.print(f"[dim]Normalized URL: {creator_url}[/dim]")

        # For TikTok and Instagram, use dedicated discovery modules
        # These ONLY discover URLs - yt-dlp does the actual download at posting time
        # URLs are saved to queue immediately; validation happens at scheduler time
        if platform == "tiktok":
            creator_url = self._normalize_tiktok_url(creator_url)
            console.print(f"[dim]TikTok username resolved: {creator_url}[/dim]")
            videos_added = self._extract_tiktok_via_discovery(creator_url)

            # After discovery, videos are already synced to session
            # Return the in-memory videos (don't reload from queue file)
            self.logger.info(f"Extracted {len(self.videos)} TikTok videos via discovery")
            return self.videos

        if platform == "instagram":
            console.print(f"[dim]Instagram profile URL resolved[/dim]")
            videos_added = self._extract_instagram_via_discovery(creator_url)

            # After discovery, videos are already synced to session
            # Return the in-memory videos (don't reload from queue file)
            self.logger.info(f"Extracted {len(self.videos)} Instagram videos via discovery")

            # Sync to session if page-scoped persistence is enabled
            if self.session_manager and self.current_session:
                self._sync_videos_to_session(self.videos, "instagram")
            return self.videos

        # Use yt-dlp to extract video information (YouTube - unchanged)
        videos = self._extract_with_yt_dlp(creator_url, platform)

        # Sort by timestamp (oldest first)
        # Use a high sentinel value for None timestamps to push them to the end
        # This ensures videos with unknown timestamps don't appear before known-old videos
        videos.sort(key=lambda v: (v.timestamp or 0) or 9999999999)

        # Update status
        for video in videos:
            video.platform = platform
            video.status = "pending"

        self.videos = videos
        self.logger.info(f"Extracted {len(videos)} videos from {creator_url}")

        # Sync to session for page-scoped persistence (YouTube needs this unlike TikTok/Instagram)
        if self.session_manager and self.current_session:
            self._sync_videos_to_session(videos, platform)

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

    def _normalize_tiktok_url(self, url: str) -> str:
        """
        Normalize TikTok URL for consistent extraction.

        TikTok @username URLs are normalized to ensure consistent format.
        Handles trailing slashes and various TikTok URL formats.
        """
        if "tiktok.com" not in url.lower():
            return url

        # Strip trailing slash for consistency
        url = url.rstrip("/")

        # Handle @username style URLs - ensure they're in canonical form
        if "@" in url:
            # Extract the username and reconstruct
            import re
            match = re.search(r'@([a-zA-Z0-9_.]+)', url)
            if match:
                username = match.group(1)
                return f"https://www.tiktok.com/@{username}"

        # Handle videos page URL
        if "/videos" in url:
            url = url.replace("/videos", "")
            return url

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

    def _extract_tiktok_via_discovery(self, profile_url: str) -> int:
        """
        Extract TikTok videos using dedicated discovery library.

        This is the primary TikTok extraction method that:
        1. Uses TikTokDiscovery to find video URLs
        2. Saves ALL discovered URLs to the persistent queue
        3. Creator setup succeeds (does NOT discard URLs due to yt-dlp validation failure)
        4. Scheduler manages downloading/posting at scheduled times

        Critically: yt-dlp metadata validation happens at posting time, NOT during discovery.
        Discovered URLs are saved even if yt-dlp cannot immediately extract metadata.

        Args:
            profile_url: TikTok profile URL (e.g., https://www.tiktok.com/@username)

        Returns:
            Number of videos added to the queue
        """
        videos_added = 0

        # Initialize TikTok discovery
        discovery = TikTokDiscovery(logger=self.logger)

        # Discover video URLs from the profile
        console.print(f"[info]{ICONS['info']} Discovering TikTok videos from profile...[/info]")
        video_infos = discovery.discover_video_urls(profile_url, max_videos=100)

        if not video_infos:
            console.print(f"[error]{ICONS['x']} No TikTok videos discovered for {self.creator_name}[/error]")
            console.print(f"[info]{ICONS['info']} The account may be private, empty, or TikTok is blocking extraction[/info]")
            return 0

        self.logger.info(f"[TIKTOK] Discovered {len(video_infos)} video URLs via discovery library")

        # Step 2: Save ALL discovered URLs to the persistent queue
        # NO yt-dlp validation during discovery - URLs are saved regardless
        console.print(f"[cyan]{ICONS['download']} Saving {len(video_infos)} TikTok video URLs to persistent queue...[/cyan]")

        seen_urls = set()
        new_videos = []

        for i, video_info in enumerate(video_infos, 1):
            video_url = video_info.url

            # Skip duplicates (by full URL)
            if video_url in seen_urls or video_url.endswith('/'):
                continue
            seen_urls.add(video_url)

            # Extract video ID from URL for deduplication
            video_id = self._extract_tiktok_video_id(video_url)

            # Create CreatorVideo with pending status
            video = CreatorVideo(
                video_url=video_url,
                title=video_info.title or f"TikTok Video {i}",
                upload_date=None,
                timestamp=video_info.upload_timestamp,
                uploader=video_info.author or self.creator_name or "unknown",
                duration=video_info.duration,
                platform="tiktok",
                status="pending",
                source_video_id=video_id,
            )

            new_videos.append(video)
            self.logger.info(f"[TIKTOK] Saved video {i}/{len(video_infos)}: {video.title[:50]}...")

        if not new_videos:
            console.print(f"[warning]{ICONS['warning']} No new unique videos to add to queue[/warning]")
            return 0

        # Add new videos to existing queue (preserving chronological order)
        # Sort new videos by timestamp (oldest first), then merge with existing
        all_videos = self.videos + new_videos
        all_videos.sort(key=lambda v: (v.timestamp or 0) or 9999999999)

        # Deduplicate by video_url, keeping first occurrence (oldest)
        final_videos = []
        seen_urls_dedup = set()
        for video in all_videos:
            if video.video_url not in seen_urls_dedup:
                final_videos.append(video)
                seen_urls_dedup.add(video.video_url)

        self.videos = final_videos
        videos_added = len(new_videos)
        # Only save to queue file if saves are enabled (session file is source of truth in creator mode)
        if self._should_save():
            self._save_queue()

        console.print(f"[success]{ICONS['check']} Added {videos_added} TikTok videos to posting queue[/success]")
        console.print(f"[info]{ICONS['info']} Total queue: {len(self.videos)} videos (chronological, oldest first)[/info]")

        # Sort by timestamp (oldest first) for the queue
        self.videos.sort(key=lambda v: (v.timestamp or 0) or 9999999999)

        # Sync to session for page-scoped persistence
        if self.session_manager and self.current_session:
            self._sync_videos_to_session(self.videos, "tiktok")

        return videos_added

    def _extract_tiktok_video_id(self, video_url: str) -> Optional[str]:
        """Extract TikTok video ID from URL for deduplication."""
        # Try to extract aweme/video ID from various TikTok URL formats
        import re

        # Handle: https://www.tiktok.com/@username/video/VIDEO_ID
        match = re.search(r'/video/([0-9]+)', video_url)
        if match:
            return match.group(1)

        # Handle: https://www.tiktok.com/v/VIDEO_ID
        match = re.search(r'/v/([0-9a-zA-Z]+)', video_url)
        if match:
            return match.group(1)

        # Handle: https://www.tiktok.com/@username/video/VISUAL-ID
        match = re.search(r'video/([^/?&]+)', video_url)
        if match:
            return match.group(1)

        # Fallback: use full URL as identifier
        return video_url.split('?')[0]

    def _extract_instagram_via_discovery(self, profile_url: str) -> int:
        """
        Extract Instagram videos using dedicated discovery library.

        This is the primary Instagram extraction method that:
        1. Uses InstagramDiscovery to find video URLs
        2. Saves ALL discovered URLs to the persistent queue
        3. Creator setup succeeds (does NOT discard URLs due to yt-dlp validation failure)
        4. Scheduler manages downloading/posting at scheduled times

        Critically: yt-dlp metadata validation happens at posting time, NOT during discovery.
        Discovered URLs are saved even if yt-dlp cannot immediately extract metadata.

        Args:
            profile_url: Instagram profile URL (e.g., https://www.instagram.com/username/)

        Returns:
            Number of videos added to the queue
        """
        videos_added = 0

        # Initialize Instagram discovery
        discovery = InstagramDiscovery(logger=self.logger)

        # Discover video URLs from the profile
        console.print(f"[info]{ICONS['info']} Discovering Instagram videos from profile...[/info]")
        media_infos = discovery.discover_video_urls(profile_url, max_videos=100)

        if not media_infos:
            console.print(f"[error]{ICONS['x']} No Instagram videos discovered for {self.creator_name}[/error]")
            console.print(f"[info]{ICONS['info']} The account may be private, empty, or Instagram is blocking extraction[/info]")
            return 0

        self.logger.info(f"[INSTAGRAM] Discovered {len(media_infos)} video URLs via discovery library")

        # Step 2: Save ALL discovered URLs to the persistent queue
        # NO yt-dlp validation during discovery - URLs are saved regardless
        console.print(f"[cyan]{ICONS['download']} Saving {len(media_infos)} Instagram video URLs to persistent queue...[/cyan]")

        seen_urls = set()
        new_videos = []

        for i, media_info in enumerate(media_infos, 1):
            video_url = media_info.url

            # Skip duplicates (by full URL)
            if video_url in seen_urls or video_url.endswith('/'):
                continue
            seen_urls.add(video_url)

            # Extract shortcode from URL for deduplication
            shortcode = media_info.shortcode

            # Create CreatorVideo with pending status
            video = CreatorVideo(
                video_url=video_url,
                title=media_info.title or f"Instagram Reel {i}",
                upload_date=None,
                timestamp=media_info.upload_timestamp,
                uploader=media_info.author or self.creator_name or "unknown",
                duration=media_info.duration,
                platform="instagram",
                status="pending",
                source_video_id=shortcode,
            )

            new_videos.append(video)
            self.logger.info(f"[INSTAGRAM] Saved video {i}/{len(media_infos)}: {video.title[:50]}...")

        if not new_videos:
            console.print(f"[warning]{ICONS['warning']} No new unique videos to add to queue[/warning]")
            return 0

        # Add new videos to existing queue (preserving chronological order)
        # Sort new videos by timestamp (oldest first), then merge with existing
        all_videos = self.videos + new_videos
        all_videos.sort(key=lambda v: (v.timestamp or 0) or 9999999999)

        # Deduplicate by video_url, keeping first occurrence (oldest)
        final_videos = []
        seen_urls_dedup = set()
        for video in all_videos:
            if video.video_url not in seen_urls_dedup:
                final_videos.append(video)
                seen_urls_dedup.add(video.video_url)

        self.videos = final_videos
        videos_added = len(new_videos)
        # Only save to queue file if saves are enabled (session file is source of truth in creator mode)
        if self._should_save():
            self._save_queue()

        console.print(f"[success]{ICONS['check']} Added {videos_added} Instagram videos to posting queue[/success]")
        console.print(f"[info]{ICONS['info']} Total queue: {len(self.videos)} videos (chronological, oldest first)[/info]")

        # Sort by timestamp (oldest first) for the queue
        self.videos.sort(key=lambda v: (v.timestamp or 0) or 9999999999)

        # Sync to session for page-scoped persistence
        if self.session_manager and self.current_session:
            self._sync_videos_to_session(self.videos, "instagram")

        return videos_added

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

        # Extract source video ID from flat playlist entry (e.g., YouTube video ID)
        source_video_id = data.get('id') or data.get('video_id') or None

        return CreatorVideo(
            video_url=data.get('webpage_url', ''),
            title=data.get('title', ''),
            upload_date=upload_date,
            timestamp=timestamp,
            uploader=data.get('uploader', ''),
            duration=data.get('duration'),
            platform=self.detect_platform(data.get('webpage_url', '')),
            source_video_id=source_video_id,
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
            if self._should_save():
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
        if self._should_save():
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

        CRITICAL: Uses discovery modules (TikTok/Instagram) which ONLY discover URLs.
        yt-dlp validation happens at posting time, NOT during re-sync.
        New URLs are added to the persistent queue regardless of immediate yt-dlp validation.

        Args:
            existing_urls: Set of video URLs already in the queue

        Returns:
            Number of new videos added
        """
        if not self.creator_url:
            console.print(f"[error]{ICONS['x']} No creator URL set. Call extract_videos() first.[/error]")
            return 0

        console.print(f"\n[cyan]{ICONS['rocket']} Re-syncing {self.creator_name} for new videos...[/cyan]")

        # Extract all videos from creator using discovery modules only
        # These modules ONLY discover URLs - yt-dlp handles download at posting time
        platform = self.detect_platform(self.creator_url)
        if platform == "tiktok":
            creator_url = self._normalize_tiktok_url(self.creator_url)
            videos_added = self._extract_tiktok_via_discovery(creator_url)
        elif platform == "instagram":
            videos_added = self._extract_instagram_via_discovery(self.creator_url)
        else:
            # YouTube - use existing yt-dlp method
            all_videos = self._extract_with_yt_dlp(self.creator_url, platform)
            # For YouTube, convert to video count
            videos_added = len(all_videos) if all_videos else 0

        if not videos_added and platform not in ("youtube",):
            console.print(f"[info]{ICONS['info']} No videos found during re-sync[/info]")
            return 0

        # For YouTube, we have actual video objects; for TikTok/Instagram, count is from discovery
        if platform == "youtube" and videos_added == 0:
            console.print(f"[info]{ICONS['info']} No videos found during re-sync[/info]")
            return 0

        # Filter to only new videos (not already in existing_urls)
        new_videos = []
        for video in self.videos:
            # Only include videos that are pending and not already in existing URLs
            # We need to check against the full queue state after re-sync
            if video.status == "pending" and video.video_url not in existing_urls:
                # Re-determine platform
                video.platform = self.detect_platform(video.video_url)
                video.status = "pending"
                new_videos.append(video)
                self.logger.info(f"New video found: {video.title}")

        if new_videos:
            # Append to existing queue (they're already there from discovery, just re-mark)
            if self._should_save():
                self._save_queue()
            console.print(f"[success]{ICONS['check']} Added {len(new_videos)} new/remaining videos from {self.creator_name}[/success]")

            # Sync new videos to session for persistence
            if self.session_manager and self.current_session:
                platform = self.detect_platform(self.creator_url) if self.creator_url else "youtube"
                self._sync_videos_to_session(new_videos, platform)
                console.print(f"[info]{ICONS['info']} Synced {len(new_videos)} new videos to session[/info]")
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
        if not self._save_enabled:
            return  # Skip saving during creator mode - session file is the source of truth

        data = {
            "creator_name": self.creator_name,
            "creator_url": self.creator_url,
            "last_sync": datetime.now().isoformat(),
            "videos": [v.to_dict() for v in self.videos],
            "total_videos": len(self.videos),
            "pending_count": sum(1 for v in self.videos if v.status == "pending"),
            "posted_count": sum(1 for v in self.videos if v.status == "posted"),
            "failed_count": sum(1 for v in self.videos if v.status == "failed"),
            "downloading_count": sum(1 for v in self.videos if v.status == "downloading"),
        }

        with open(self.queue_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _session_video_to_creator_video(self, session_video: 'SessionVideo') -> 'CreatorVideo':
        """
        Convert a SessionVideo back to a CreatorVideo for runtime operations.

        This is used when loading an existing session to sync the persisted
        videos back to the in-memory queue for continued operations.
        """
        return CreatorVideo(
            video_url=session_video.video_url,
            title=session_video.title,
            upload_date=session_video.upload_date,
            timestamp=session_video.timestamp,
            platform=session_video.platform,
            status=session_video.status.value,  # Convert enum to string
            posted_at=session_video.posted_at,
            content_id=session_video.content_id,
            download_attempts=session_video.download_attempts,
            source_video_id=session_video.source_video_id,
        )

    def sync_session_to_memory(self):
        """
        Sync loaded session videos to in-memory queue.

        This ensures the in-memory videos list matches the persisted session,
        enabling continued operations after restart.
        """
        if not self.current_session:
            self.logger.warning("[SESSION] No current_session to sync to memory")
            return

        if not self.page_id:
            self.logger.warning("[SESSION] page_id not set - cannot sync session to memory")
            return

        loaded_count = len(self.current_session.videos)
        self.videos = [
            self._session_video_to_creator_video(sv)
            for sv in self.current_session.videos
        ]
        self.creator_url = self.current_session.creator_url
        self.creator_name = self.current_session.creator_name
        self.logger.info(f"[SESSION] Synced {loaded_count} videos from session to memory for page {self.page_id}")

    def _creator_video_to_session_video(self, video: CreatorVideo) -> SessionVideo:
        """
        Convert a CreatorVideo to a SessionVideo for page-scoped persistence.
        """
        if not self.page_id:
            self.logger.warning(f"Cannot create session video - no page_id set")
            return None

        # Generate page-scoped video ID
        if video.source_video_id:
            platform = video.platform or "unknown"
            video_id = self.session_manager.generate_video_id(platform, video.source_video_id)
        else:
            # Fallback: hash the URL
            import hashlib
            video_id = f"{video.platform}_{hashlib.md5((self.page_id + video.video_url).encode()).hexdigest()[:16]}"

        self.logger.debug(f"[SESSION] Converting CreatorVideo -> SessionVideo: {video_id}")

        return SessionVideo(
            video_id=video_id,
            video_url=video.video_url,
            title=video.title,
            session_id=self.current_session.session_id if self.current_session else None,
            upload_date=video.upload_date,
            timestamp=video.timestamp,
            platform=video.platform,
            status=VideoStatus.PENDING,
            content_id=video.content_id,
            posted_at=video.posted_at,
            download_attempts=video.download_attempts,
            retry_count=0,
            error_message="",
            source_video_id=video.source_video_id,
        )

    def _sync_videos_to_session(self, videos: List[CreatorVideo], platform: str) -> bool:
        """
        Sync videos to the page-scoped session for persistent tracking.

        This ensures video status is tracked per-page and survives crashes.
        """
        if not self.session_manager or not self.current_session:
            return False

        try:
            # Add any new videos directly to the in-memory session
            for video in videos:
                if video.status == "pending":
                    session_video = self._creator_video_to_session_video(video)
                    if session_video:
                        # Check if already in session by video_id
                        if not self.current_session.get_video_by_id(session_video.video_id):
                            session_video.status = VideoStatus.PENDING
                            session_video.platform = video.platform
                            session_video.source_video_id = video.source_video_id
                            # Add directly to in-memory session
                            self.current_session.videos.append(session_video)
                            # Update queue_order
                            if session_video.video_id not in self.current_session.queue_order:
                                self.current_session.queue_order.append(session_video.video_id)

            # Update total_videos count
            self.current_session.total_videos = len(self.current_session.videos)

            # Save the session immediately
            self.session_manager.save_session(self.current_session)
            return True
        except Exception as e:
            self.logger.error(f"Failed to sync videos to session: {e}")
            return False

    def create_session(self, platform: str) -> Optional[CreatorSession]:
        """
        Create a new session for the current page.

        Args:
            platform: The platform name (youtube, tiktok, instagram)

        Returns:
            The created session if page_id is set, None otherwise
        """
        if not self.page_id or not self.session_manager:
            return None

        session = self.session_manager.create_new_session(
            creator_url=self.creator_url,
            creator_name=self.creator_name,
            platform=platform,
            page_id=self.page_id,
        )

        # Save the new session
        self.session_manager.save_session(session)
        self.current_session = session
        return session

    def update_session_status(self, status: str) -> bool:
        """
        Update the current session status.

        Args:
            status: The new status (setup, active, paused, completed, failed)

        Returns:
            True if successful, False if no session
        """
        if not self.current_session:
            return False

        from src.creator.session import SessionStatus

        try:
            status_enum = SessionStatus(status)
            self.current_session.status = status_enum
            return self.session_manager.save_session(self.current_session)
        except ValueError:
            self.logger.error(f"Invalid session status: {status}")
            return False

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
        if self._should_save():
            self._save_queue()

    def mark_as_downloading(self, video: CreatorVideo):
        """Mark a video as currently being downloaded."""
        video.status = "downloading"
        video.download_attempts += 1
        if self._should_save():
            self._save_queue()

    def mark_as_downloaded(self, video: CreatorVideo):
        """Mark a video as successfully downloaded."""
        video.status = "downloaded"
        if self._should_save():
            self._save_queue()

    def mark_as_failed(self, video: CreatorVideo, error: str = ""):
        """Mark a video as failed."""
        video.status = "failed"
        if self._should_save():
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
        if self._should_save():
            self._save_queue()

    def reset_queue(self):
        """Reset the queue - all videos become pending."""
        for video in self.videos:
            video.status = "pending"
            video.posted_at = None
            video.content_id = None
        if self._should_save():
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