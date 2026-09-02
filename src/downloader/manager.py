"""
Video Downloader Module
Handles downloading content from Instagram, TikTok, and other platforms.
Uses platform-specific libraries: yt-dlp for YouTube and TikTok,
and instaloader for Instagram.
"""

import json
import logging
import subprocess
import shutil
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import uuid

import instaloader


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


def _download_instagram_with_instaloader(url: str, downloader: 'VideoDownloader') -> Optional[Path]:
    """
    Download an Instagram reel/post using instaloader.

    Uses instaloader.Instaloader.download_post() to download the media.

    Args:
        url: Instagram reel/post URL (e.g., https://www.instagram.com/reel/Shortcode/)
        downloader: VideoDownloader instance for folder path

    Returns:
        Path to the downloaded media file, or None on failure
    """
    try:
        # Extract shortcode from URL
        # Supported formats:
        # - https://www.instagram.com/reel/Shortcode/
        # - https://www.instagram.com/p/Shortcode/
        # - https://www.instagram.com/tv/Shortcode/
        shortcode = None
        import re

        # Try to extract shortcode from various URL formats
        reel_match = re.search(r'instagram\.com/reel/([a-zA-Z0-9_]+)', url)
        post_match = re.search(r'instagram\.com/p/([a-zA-Z0-9_]+)', url)
        tv_match = re.search(r'instagram\.com/tv/([a-zA-Z0-9_]+)', url)

        if reel_match:
            shortcode = reel_match.group(1)
        elif post_match:
            shortcode = post_match.group(1)
        elif tv_match:
            shortcode = tv_match.group(1)

        if not shortcode:
            downloader.logger.warning(f"Could not extract shortcode from Instagram URL: {url}")
            return None

        # Create instaloader instance
        L = instaloader.Instaloader(
            quiet=True,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
        )

        # Get post from shortcode
        try:
            post = instaloader.Post.from_shortcode(L.context, shortcode)
        except Exception as e:
            downloader.logger.error(f" instaloader failed to fetch post {shortcode}: {e}")
            return None

        # Download post - target is the download folder
        # instaloader will save the file with a name based on shortcode
        downloader.logger.info(f"Downloading Instagram reel {shortcode} with instaloader...")
        downloaded = L.download_post(post, target=str(downloader.download_folder))

        if not downloaded:
            downloader.logger.warning(" instaloader download returned False")
            return None

        # Find the downloaded file in the download folder
        # instaloader saves files in the target directory
        # Look for mp4 or video files
        media_files = list(downloader.download_folder.rglob("*"))
        media_files = [f for f in media_files if f.is_file() and f.suffix.lower() in ['.mp4', '.webm'] and f.stat().st_size > 0]

        if not media_files:
            # Also check subdirectories
            for subdir in downloader.download_folder.rglob("*"):
                if subdir.is_dir():
                    for f in subdir.rglob("*"):
                        if f.is_file() and f.suffix.lower() in ['.mp4', '.webm'] and f.stat().st_size > 0:
                            media_files.append(f)

        if not media_files:
            downloader.logger.warning(" instaloader download completed but no media file found")
            return None

        # Return the largest media file
        main_file = max(media_files, key=lambda f: f.stat().st_size)
        downloader.logger.info(f" instaloader downloaded Instagram media to: {main_file}")
        return main_file

    except ImportError as e:
        downloader.logger.error(f" instaloader import failed: {e}")
        return None
    except Exception as e:
        downloader.logger.error(f" instaloader Instagram download failed: {e}")
        return None


class VideoDownloader:
    """
    Downloads videos and content from Instagram, TikTok, and other platforms.
    Uses platform-specific libraries: yt-dlp for YouTube and TikTok,
    and instaloader for Instagram.
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

        Uses platform-specific downloaders:
        - YouTube: yt-dlp
        - TikTok: yt-dlp
        - Instagram: instaloader

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

        # Generate unique ID for this download
        download_id = str(uuid.uuid4())[:12]

        # Platform-specific download dispatch
        if platform == Platform.TIKTOK:
            return self._download_tiktok(url, download_id, custom_title)
        elif platform == Platform.INSTAGRAM:
            return self._download_instagram(url, download_id, custom_title)
        else:
            return self._download_youtube(url, download_id, quality, extract_audio, custom_title)

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

        # Add cookies file when enabled to bypass bot detection
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

        # YouTube-specific options only (Instagram uses instaloader, TikTok uses yt-dlp)
        if "youtube.com" in url or "youtu.be" in url or "yt.be" in url:
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

    def _download_tiktok(self, url: str, download_id: str, custom_title: Optional[str] = None, quality: str = "best", extract_audio: bool = False) -> Optional[DownloadedContent]:
        """
        Download TikTok video using yt-dlp Python API.

        Args:
            url: TikTok video URL
            download_id: Unique ID for this download
            custom_title: Optional custom title for the video
            quality: Video quality preference (best, 1080p, 720p, 480p, audio)
            extract_audio: Whether to extract audio only

        Returns:
            DownloadedContent object or None on failure
        """
        platform = Platform.TIKTOK

        # Create output directory for this download
        output_dir = self.download_folder / download_id
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            self.logger.info(f"Downloading TikTok video with yt-dlp: {url}")

            import yt_dlp
            from yt_dlp.utils import DownloadError

            # Build yt-dlp options for TikTok
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'writeinfojson': True,
                'writethumbnail': True,
                'outtmpl': str(output_dir / '%(id)s.%(ext)s'),
                'format': 'bestvideo+bestaudio/best' if not extract_audio else 'bestaudio/best',
                'merge_output_format': 'mp4' if not extract_audio else 'mp3',
                'logger': type('Logger', (), {
                    'debug': lambda s, m: None,
                    'info': lambda s, m: None,
                    'warning': lambda s, m: None,
                    'error': lambda s, m: None,
                })(),
            }

            # Add cookies support like YouTube
            # yt-dlp Python API uses 'cookiefile' (singular) for cookie file path
            if self.use_cookies_file and Path(self.cookies_file).exists():
                ydl_opts['cookiefile'] = self.cookies_file

            if extract_audio:
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]

            # Download the video
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

            if not info:
                error_msg = "yt-dlp failed to extract video info"
                self.logger.error(error_msg)
                return self._create_failed_content(download_id, platform, url, error_msg)

            # Find downloaded media files
            downloaded_files = list(output_dir.rglob("*"))
            media_files = [f for f in downloaded_files if f.is_file() and f.suffix.lower() in ['.mp4', '.webm', '.mkv', '.m4a', '.mp3', '.wav', '.mp4']]

            if not media_files:
                error_msg = f"yt-dlp download completed but no media file found at {output_dir}"
                self.logger.error(error_msg)
                return self._create_failed_content(download_id, platform, url, error_msg)

            # Get the main media file (largest file - usually the video)
            main_file = max(media_files, key=lambda f: f.stat().st_size)

            # Load metadata from info file
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

            # Get file size and mime type
            file_size = main_file.stat().st_size
            mime_type = self._get_mime_type(main_file)

            # Try to find thumbnail
            thumb_files = [f for f in media_files if f.suffix.lower() in ['.jpg', '.jpeg', '.png', '.webp']]
            thumbnail_path = thumb_files[0] if thumb_files else None

            content = DownloadedContent(
                id=download_id,
                platform=platform,
                original_url=url,
                title=title,
                description=description,
                file_path=main_file,
                thumbnail_path=thumbnail_path,
                file_size=file_size,
                mime_type=mime_type,
                duration=duration,
                metadata={
                    **metadata,
                    'uploader': uploader,
                    'upload_date': upload_date,
                    'platform': platform.value,
                    'downloaded_by': 'yt-dlp'
                }
            )

            self.download_history.append(content)
            self.logger.info(f"Downloaded TikTok video successfully: {title}")
            return content

        except DownloadError as e:
            error_msg = f"Download failed: {str(e)}"
            if "bot" in str(e).lower() or "sign in" in str(e).lower():
                enhanced_error = f"TikTok bot detection triggered.\n\nSolution: Your cookies.txt file may need to be updated.\nPlease refresh your cookies from your browser and replace the existing file.\n\nOriginal error: {error_msg}"
                self.logger.error(enhanced_error)
            else:
                self.logger.error(error_msg)
            return self._create_failed_content(download_id, platform, url, error_msg)
        except Exception as e:
            error_msg = f"TikTok download error: {str(e)}"
            self.logger.error(error_msg)
            return self._create_failed_content(download_id, platform, url, error_msg)

    def _download_instagram(self, url: str, download_id: str, custom_title: Optional[str] = None) -> Optional[DownloadedContent]:
        """
        Download Instagram video using instaloader.

        Args:
            url: Instagram reel/post URL
            download_id: Unique ID for this download
            custom_title: Optional custom title for the video

        Returns:
            DownloadedContent object or None on failure
        """
        platform = Platform.INSTAGRAM

        try:
            # Use instaloader to download
            result = _download_instagram_with_instaloader(url, self)

            if not result or not result.exists():
                error_msg = "instaloader failed to download Instagram media"
                self.logger.error(error_msg)
                return self._create_failed_content(download_id, platform, url, error_msg)

            # Get metadata from file info
            media_file = result
            file_size = media_file.stat().st_size
            mime_type = self._get_mime_type(media_file)

            # Extract title from filename or use custom
            title = media_file.stem
            if custom_title:
                title = custom_title

            self.download_history.append(DownloadedContent(
                id=download_id,
                platform=platform,
                original_url=url,
                title=title,
                description="",  # No description from instaloader
                file_path=media_file,
                file_size=file_size,
                mime_type=mime_type,
                metadata={
                    'platform': platform.value,
                    'downloaded_by': 'instaloader'
                }
            ))

            self.logger.info(f"Downloaded Instagram media successfully: {title}")
            return self.download_history[-1]

        except Exception as e:
            error_msg = f"Instagram download error: {str(e)}"
            self.logger.error(error_msg)
            return self._create_failed_content(download_id, platform, url, error_msg)

    def _download_youtube(self, url: str, download_id: str, quality: str, extract_audio: bool, custom_title: Optional[str] = None) -> Optional[DownloadedContent]:
        """
        Download YouTube video using yt-dlp.

        Original implementation preserved for YouTube.

        Args:
            url: YouTube video URL
            download_id: Unique ID for this download
            quality: Video quality preference
            extract_audio: Whether to extract audio only
            custom_title: Optional custom title for the video

        Returns:
            DownloadedContent object or None on failure
        """
        platform = Platform.YOUTUBE

        # Check for cookies.txt file if needed
        if self.use_cookies_file:
            cookies_path = Path(self.cookies_file)
            if not cookies_path.exists():
                error_msg = f"YouTube download requires cookies.txt file.\n\nPlease create a 'cookies.txt' file in the project directory.\nLocation: {cookies_path.absolute()}\n\nSee COOKIES_GUIDE.md for instructions on how to extract cookies from your browser."
                self.logger.error(error_msg)
                return self._create_failed_content(download_id, platform, url, error_msg)

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
                errors='replace',
                timeout=300
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