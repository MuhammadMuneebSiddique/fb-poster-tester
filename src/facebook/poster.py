"""
Facebook Poster Module
Handles posting content to Facebook using the Graph API client.
"""

import logging
import os
import time
import random
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime

from src.content.manager import ContentManager, ContentType
from src.facebook.client import FacebookClient


class FacebookPoster:
    """
    Handles posting content to Facebook Pages.

    Supports text, image, video, and link posts with retry logic.
    """

    def __init__(
        self,
        client: FacebookClient,
        content_manager: ContentManager,
        logger: Optional[logging.Logger] = None,
        advanced_config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize the Facebook Poster.

        Args:
            client: Facebook Graph API client
            content_manager: Content manager instance
            logger: Logger instance
            advanced_config: Advanced configuration options
        """
        self.client = client
        self.content_manager = content_manager
        self.logger = logger or logging.getLogger(__name__)
        self.advanced_config = advanced_config or {}

        # Retry configuration
        self.max_retries = self.advanced_config.get("max_retries", 3)
        self.retry_delay = self.advanced_config.get("retry_delay", 60)
        self.retry_backoff = self.advanced_config.get("retry_backoff", 2)
        self.max_retry_delay = self.advanced_config.get("max_retry_delay", 3600)

        # Dry run mode
        self.dry_run = self.advanced_config.get("dry_run", False)

        # Post statistics
        self.posts_made = 0
        self.posts_failed = 0

    def post_content(self, content_id: str) -> bool:
        """
        Post content by ID.

        Args:
            content_id: ID of content to post

        Returns:
            True if successful, False otherwise
        """
        content = self.content_manager.get_content(content_id)
        if not content:
            self.logger.error(f"Content not found: {content_id}")
            return False

        self.logger.info(f"Posting content: {content.title} ({content.type.value})")

        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would post: {content.title}")
            return True

        # Determine post method based on content type
        try:
            if content.type == ContentType.TEXT:
                result = self._post_text(content)
            elif content.type == ContentType.IMAGE:
                result = self._post_image(content)
            elif content.type == ContentType.VIDEO:
                result = self._post_video(content)
            elif content.type == ContentType.LINK:
                result = self._post_link(content)
            else:
                self.logger.error(f"Unsupported content type: {content.type}")
                return False

            if result:
                self.posts_made += 1
                content.last_posted = datetime.now().isoformat()
                content.post_count += 1
                self.logger.info(f"Successfully posted: {content.title}")
                return True
            else:
                self.posts_failed += 1
                return False

        except Exception as e:
            self.posts_failed += 1
            self.logger.error(f"Error posting content {content_id}: {e}", exc_info=True)
            return False

    def _post_text(self, content) -> bool:
        """Post text content."""
        message = content.message or self.advanced_config.get("default_text", "")

        # Add hashtags if configured
        hashtags = self.advanced_config.get("default_hashtags", "")
        if hashtags and not message.endswith(hashtags):
            message = f"{message}\n\n{hashtags}"

        result = self.client.post_text(message)
        return result is not None

    def _post_image(self, content) -> bool:
        """Post image content."""
        message = content.message or ""
        hashtags = self.advanced_config.get("default_hashtags", "")
        if hashtags and not message.endswith(hashtags):
            message = f"{message}\n\n{hashtags}"

        result = self.client.post_image(str(content.path), message=message)
        return result is not None

    def _post_video(self, content) -> bool:
        """Post video content."""
        title = content.metadata.get("title", content.title)
        description = content.message or content.metadata.get("description", "")

        # Add hashtags to description
        hashtags = self.advanced_config.get("default_hashtags", "")
        if hashtags and not description.endswith(hashtags):
            description = f"{description}\n\n{hashtags}"

        result = self.client.post_video(
            str(content.path),
            title=title,
            description=description
        )
        return result is not None

    def _post_link(self, content) -> bool:
        """Post link content."""
        link = content.metadata.get("link", "")
        if not link:
            self.logger.error(f"No link found for content: {content.id}")
            return False

        message = content.message or ""
        hashtags = self.advanced_config.get("default_hashtags", "")
        if hashtags and not message.endswith(hashtags):
            message = f"{message}\n\n{hashtags}"

        result = self.client.post_link(link, message=message)
        return result is not None

    def post_now(self, content_id: str) -> bool:
        """
        Post content immediately (alias for post_content).

        Args:
            content_id: Content ID to post

        Returns:
            True if successful
        """
        return self.post_content(content_id)

    def schedule_post(
        self,
        content_id: str,
        publish_time: datetime
    ) -> bool:
        """
        Schedule a post for future publishing.

        Args:
            content_id: Content to schedule
            publish_time: When to publish (datetime)

        Returns:
            True if scheduled successfully
        """
        content = self.content_manager.get_content(content_id)
        if not content:
            self.logger.error(f"Content not found: {content_id}")
            return False

        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would schedule: {content.title} at {publish_time}")
            return True

        timestamp = int(publish_time.timestamp())

        try:
            if content.type == ContentType.TEXT:
                message = content.message or ""
                result = self.client.post_text(message, published=False, scheduled_publish_time=timestamp)
            elif content.type == ContentType.IMAGE:
                message = content.message or ""
                result = self.client.post_image(str(content.path), message=message, published=False, scheduled_publish_time=timestamp)
            elif content.type == ContentType.VIDEO:
                title = content.metadata.get("title", content.title)
                description = content.message or content.metadata.get("description", "")
                result = self.client.post_video(str(content.path), title=title, description=description, published=False, scheduled_publish_time=timestamp)
            elif content.type == ContentType.LINK:
                link = content.metadata.get("link", "")
                message = content.message or ""
                result = self.client.post_link(link, message=message, published=False, scheduled_publish_time=timestamp)
            else:
                return False

            if result:
                self.logger.info(f"Scheduled post: {content.title} for {publish_time}")
                return True

            return False

        except Exception as e:
            self.logger.error(f"Error scheduling post: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get posting statistics."""
        return {
            "posts_made": self.posts_made,
            "posts_failed": self.posts_failed,
            "success_rate": (
                self.posts_made / (self.posts_made + self.posts_failed) * 100
                if (self.posts_made + self.posts_failed) > 0 else 0
            )
        }

    def reset_stats(self):
        """Reset posting statistics."""
        self.posts_made = 0
        self.posts_failed = 0