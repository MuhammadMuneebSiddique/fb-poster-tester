"""
Video Downloader Module
Handles downloading content from various platforms using yt-dlp with cookie support.
"""

from .manager import VideoDownloader, DownloadedContent, DownloadStatus, Platform, create_downloader

__all__ = ['VideoDownloader', 'DownloadedContent', 'DownloadStatus', 'Platform', 'create_downloader']