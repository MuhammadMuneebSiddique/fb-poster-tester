"""
Creator URL Discovery Module

Provides platform-specific URL discovery for TikTok and Instagram profiles.
These discovery classes ONLY return video URLs - they do NOT download videos.
"""

from src.creator.discovery.tiktok_discovery import TikTokDiscovery, TikTokVideoInfo
from src.creator.discovery.instagram_discovery import InstagramDiscovery, InstagramMediaInfo

__all__ = [
    'TikTokDiscovery',
    'TikTokVideoInfo',
    'InstagramDiscovery',
    'InstagramMediaInfo',
]