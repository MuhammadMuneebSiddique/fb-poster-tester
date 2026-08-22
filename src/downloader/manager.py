"""
Video Downloader Module
Handles downloading content from Instagram, TikTok, and other platforms using yt-dlp.
"""

import os
import json
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid


class Platform(Enum):
    """Supported platforms for downloading."""
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    YOUTUBE = "youtube"
    UNKNOWN = "unknown"


class DownloadStatus(Enum):
    """Download status enumeration."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DownloadedContent:
    """Represents a downloaded content item."""
    id: str
    platform: Platform
    original_url: str
    title: str
    description: str
    file_path: Path
    thumbnail_path: Optional[Path] = None
    file_size: int = 0
    mime_type: str = ""
    duration: Optional[float] = None
    downloaded_at: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    status: DownloadStatus = DownloadStatus.COMPLETED
    error_message: str = ""


class VideoDownloader:
    """
    Downloads videos and content from Instagram, TikTok, and other platforms using yt-dlp.
    """

    def __init__(
        self,
        download_folder: str = "downloads",
        logger: Optional[logging.Logger] = None,
        use_cookies_file: bool = True,
        cookies_file: str = "cookies.txt"
    ):
        """
        Initialize the Video Downloader.

        Args:
            download_folder: Folder to save downloaded content
            logger: Logger instance
            use_cookies_file: Whether to use cookies.txt file for YouTube authentication
            cookies_file: Path to cookies.txt file
        """
        self.download_folder = Path(download_folder)
        self.logger = logger or logging.getLogger(__name__)
        self.use_cookies_file = use_cookies_file
        self.cookies_file = cookies_file
        self.download_folder.mkdir(parents=True, exist_ok=True)

        # Check if yt-dlp is available
        self._check_yt_dlp()

        # Track downloads
        self.download_history: List[DownloadedContent] = []

    def _check_yt_dlp(self) -> bool:
        """Check if yt-dlp is installed and available."""
        try:
            result = subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                self.logger.info(f"yt-dlp version: {result.stdout.strip()}")
                return True
            else:
                self.logger.error("yt-dlp not found")
                return False
        except FileNotFoundError:
            self.logger.error("yt-dlp not installed. Install with: pip install yt-dlp")
            return False
        except Exception as e:
            self.logger.error(f"Error checking yt-dlp: {e}")
            return False

    def detect_platform(self, url: str) -> Platform:
        """Detect platform from URL."""
        url_lower = url.lower()
        if "instagram.com" in url_lower or "instagr.am" in url_lower:
            return Platform.INSTAGRAM
        elif "tiktok.com" in url_lower:
            return Platform.TIKTOK
        elif "youtube.com" in url_lower or "youtu.be" in url_lower:
            return Platform.YOUTUBE
        return Platform.UNKNOWN

    def download(
        self,
        url: str,
        custom_title: Optional[str] = None,
        quality: str = "best",
        extract_audio: bool = False
    ) -> Optional[DownloadedContent]:
        """
        Download content from a URL.

        Args:
            url: Video/post URL to download
            custom_title: Optional custom title
            quality: Video quality (best, 1080p, 720p, 480p, audio)
            extract_audio: Whether to extract audio only

        Returns:
            DownloadedContent object or None on failure
        """
        platform = self.detect_platform(url)
        self.logger.info(f"Downloading from {platform.value}: {url}")

        # Check for cookies.txt file if needed for YouTube
        if self.use_cookies_file and platform == Platform.YOUTUBE:
            cookies_path = Path(self.cookies_file)
            if not cookies_path.exists():
                error_msg = f"YouTube download requires cookies.txt file.\n\nPlease create a 'cookies.txt' file in the project directory.\nLocation: {cookies_path.absolute()}\n\nSee COOKIES_GUIDE.md for instructions on how to extract cookies from your browser."
                self.logger.error(error_msg)
                return self._create_failed_content(str(uuid.uuid4())[:12], platform, url, error_msg)

        # Generate unique ID for this download
        download_id = str(uuid.uuid4())[:12]
        output_dir = self.download_folder / download_id
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Build yt-dlp command
            cmd = self._build_command(url, output_dir, quality, extract_audio)

            self.logger.debug(f"Running command: {' '.join(cmd)}")

            # Run yt-dlp
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',  # Replace invalid chars instead of crashing
                timeout=300  # 5 minute timeout
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip()

                # Provide helpful guidance for YouTube bot detection errors
                if "Sign in to confirm you're not a bot" in error_msg or "sign in" in error_msg.lower():
                    enhanced_error = f"YouTube bot detection triggered.\n\nSolution: Your cookies.txt file may need to be updated.\nPlease refresh your cookies from your browser and replace the existing file.\n\nOriginal error: {error_msg}"
                    self.logger.error(enhanced_error)
                # Provide helpful guidance for format errors
                elif "Requested format is not available" in error_msg or "format" in error_msg.lower():
                    enhanced_error = f"YouTube format not available for this video.\n\nSolution: yt-dlp tried to use a specific format that doesn't exist for this video (common with YouTube Shorts).\nThe download will retry with the best available format.\n\nOriginal error: {error_msg}"
                    self.logger.warning(enhanced_error)
                    # Retry with best format
                    cmd = self._build_command(url, output_dir, "best", extract_audio)
                    self.logger.debug(f"Retrying with command: {' '.join(cmd)}")
                    result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=300)
                    if result.returncode != 0:
                        return self._create_failed_content(download_id, platform, url, result.stderr.strip())
                else:
                    self.logger.error(f"Download failed: {error_msg}")

                return self._create_failed_content(download_id, platform, url, error_msg)

            # Find downloaded files
            downloaded_files = list(output_dir.rglob("*"))
            media_files = [f for f in downloaded_files if f.is_file() and not f.name.endswith(('.json', '.info', '.meta'))]

            if not media_files:
                self.logger.error("No media files found after download")
                return self._create_failed_content(download_id, platform, url, "No media files found")

            # Get the main media file (largest file usually)
            main_file = max(media_files, key=lambda f: f.stat().st_size)

            # Load metadata from yt-dlp info file
            info_file = output_dir / f"{main_file.stem}.info.json"
            metadata = {}
            if info_file.exists():
                try:
                    with open(info_file, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                except Exception as e:
                    self.logger.warning(f"Failed to load metadata: {e}")

            # Extract info from metadata
            title = custom_title or metadata.get('title', main_file.stem)
            description = metadata.get('description', '')
            duration = metadata.get('duration')
            uploader = metadata.get('uploader', '')
            upload_date = metadata.get('upload_date', '')

            # Create DownloadedContent object
            content = DownloadedContent(
                id=download_id,
                platform=platform,
                original_url=url,
                title=title,
                description=description,
                file_path=main_file,
                file_size=main_file.stat().st_size,
                mime_type=self._get_mime_type(main_file),
                duration=duration,
                metadata={
                    **metadata,
                    'uploader': uploader,
                    'upload_date': upload_date,
                    'platform': platform.value,
                    'downloaded_by': 'yt-dlp'
                }
            )

            # Try to find thumbnail
            thumb_files = [f for f in media_files if f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']]
            if thumb_files:
                content.thumbnail_path = thumb_files[0]

            self.download_history.append(content)
            self.logger.info(f"Downloaded successfully: {title} ({main_file.name})")
            return content

        except subprocess.TimeoutExpired:
            error_msg = "Download timeout (5 minutes)"
            self.logger.error(error_msg)
            return self._create_failed_content(download_id, platform, url, error_msg)
        except Exception as e:
            error_msg = f"Download error: {str(e)}"
            self.logger.error(error_msg)
            return self._create_failed_content(download_id, platform, url, error_msg)

    def _build_command(
        self,
        url: str,
        output_dir: Path,
        quality: str,
        extract_audio: bool
    ) -> List[str]:
        """Build yt-dlp command."""
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--write-info-json",
            "--write-thumbnail",
            "--no-warnings",
            "-o", str(output_dir / "%(title)s.%(ext)s"),
        ]

        # Add cookies file for YouTube when enabled to bypass bot detection
        if self.use_cookies_file and ("youtube.com" in url or "youtu.be" in url or "yt.be" in url):
            cmd.extend(["--cookies", self.cookies_file])
            self.logger.info(f"Using cookies file: {self.cookies_file} for YouTube authentication")

        # Quality settings - Robust format selection that works for YouTube Shorts and regular videos
        # YouTube Shorts require special handling - they have formats but height filters can fail
        if extract_audio or quality == "audio":
            cmd.extend([
                "-x",
                "--audio-format", "mp3",
                "--audio-quality", "192K",
            ])
            cmd.extend(["-f", "best[height<=1080]/best"])
        elif quality == "1080p":
            # For YouTube Shorts, use combined format first (avoids "Requested format is not available")
            # The format chain tries: 1080p combined -> best up to 1080 -> best overall
            cmd.extend(["-f", "best[height<=1080]/best[height<=1080]/best"])
        elif quality == "720p":
            cmd.extend(["-f", "best[height<=720]/best[height<=720]/best"])
        elif quality == "480p":
            cmd.extend(["-f", "best[height<=480]/best[height<=480]/best"])
        else:
            # Default: best format - yt-dlp automatically picks the optimal format for each video
            cmd.extend(["-f", "best"])

        # Platform-specific options
        if "instagram.com" in url:
            cmd.extend(["--extractor-args", "instagram:api_version=v1"])
        elif "tiktok.com" in url:
            cmd.extend(["--extractor-args", "tiktok:api_version=v1"])
        elif "youtube.com" in url or "youtu.be" in url or "yt.be" in url:
            # YouTube-specific options for better compatibility
            cmd.extend([
                "--extractor-args", "youtube:player_client=android",
            ])

        cmd.append(url)
        return cmd

    def _get_mime_type(self, file_path: Path) -> str:
        """Get MIME type from file extension."""
        ext = file_path.suffix.lower()
        mime_map = {
            '.mp4': 'video/mp4',
            '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo',
            '.mkv': 'video/x-matroska',
            '.webm': 'video/webm',
            '.mp3': 'audio/mpeg',
            '.m4a': 'audio/mp4',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.webp': 'image/webp',
        }
        return mime_map.get(ext, 'application/octet-stream')

    def _create_failed_content(
        self,
        download_id: str,
        platform: Platform,
        url: str,
        error_message: str
    ) -> DownloadedContent:
        """Create a failed download record."""
        content = DownloadedContent(
            id=download_id,
            platform=platform,
            original_url=url,
            title="",
            description="",
            file_path=Path(""),
            status=DownloadStatus.FAILED,
            error_message=error_message
        )
        self.download_history.append(content)
        return content

    def download_multiple(
        self,
        urls: List[str],
        quality: str = "best",
        extract_audio: bool = False
    ) -> List[DownloadedContent]:
        """
        Download multiple URLs.

        Args:
            urls: List of URLs to download
            quality: Video quality
            extract_audio: Whether to extract audio only

        Returns:
            List of DownloadedContent objects
        """
        results = []
        for i, url in enumerate(urls):
            self.logger.info(f"Downloading {i+1}/{len(urls)}: {url}")
            content = self.download(url, quality=quality, extract_audio=extract_audio)
            results.append(content)
        return results

    def get_download_history(self) -> List[DownloadedContent]:
        """Get download history."""
        return self.download_history

    def clear_history(self):
        """Clear download history."""
        self.download_history.clear()

    def cleanup_failed_downloads(self):
        """Remove failed download directories."""
        for content in self.download_history:
            if content.status == DownloadStatus.FAILED and content.file_path.exists():
                try:
                    shutil.rmtree(content.file_path.parent)
                    self.logger.info(f"Cleaned up failed download: {content.id}")
                except Exception as e:
                    self.logger.warning(f"Failed to cleanup {content.id}: {e}")


def create_downloader(
    download_folder: str = "downloads",
    logger: Optional[logging.Logger] = None,
    use_cookies_file: bool = True,
    cookies_file: str = "cookies.txt"
) -> VideoDownloader:
    """
    Factory function to create VideoDownloader.

    Args:
        download_folder: Folder to save downloaded content
        logger: Logger instance
        use_cookies_file: Whether to use cookies.txt file for YouTube authentication
        cookies_file: Path to cookies.txt file

    Returns:
        VideoDownloader instance
    """
    return VideoDownloader(download_folder, logger, use_cookies_file, cookies_file)