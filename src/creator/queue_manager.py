"""
Queue Manager
Manages the posting queue for content creator videos.

During creator mode, the session file is the single source of truth.
The queue reads from and updates the session, which handles persistence.
"""

import os
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass, field

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from src.ui.console import console, ICONS


@dataclass
class QueueItem:
    """
    Represents an item in the posting queue.

    Each item is scoped to:
    - page_id: The Facebook Page this video is for
    - session_id: The creator session this video belongs to
    - video_id: The unique video identifier (platform-scoped)
    """
    id: str
    video_url: str
    title: str
    page_id: Optional[str] = None  # Page-scoped video ID for multi-page isolation
    session_id: Optional[str] = None  # Creator session this item belongs to
    video_id: Optional[str] = None  # Page-scoped video identifier (page_id + platform + source_video_id hash)
    source_video_id: Optional[str] = None  # Platform-specific video ID (YouTube video ID, TikTok aweme ID, etc.)
    platform: Optional[str] = None  # youtube, tiktok, instagram
    upload_date: Optional[str] = None
    timestamp: Optional[float] = None
    scheduled_order: int = 0  # Order in which it should be posted
    status: str = "pending"  # pending, downloading, posted, failed
    posted_at: Optional[str] = None
    scheduled_time: Optional[str] = None  # HH:MM format
    scheduled_days: List[str] = field(default_factory=lambda: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "video_url": self.video_url,
            "title": self.title,
            "page_id": self.page_id,
            "session_id": self.session_id,
            "video_id": self.video_id,
            "source_video_id": self.source_video_id,
            "platform": self.platform,
            "upload_date": self.upload_date,
            "timestamp": self.timestamp,
            "scheduled_order": self.scheduled_order,
            "status": self.status,
            "posted_at": self.posted_at,
            "scheduled_time": self.scheduled_time,
            "scheduled_days": self.scheduled_days,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueueItem':
        """Create from dictionary."""
        return cls(
            id=data.get("id", ""),
            video_url=data.get("video_url", ""),
            title=data.get("title", ""),
            page_id=data.get("page_id"),
            session_id=data.get("session_id"),
            video_id=data.get("video_id"),
            source_video_id=data.get("source_video_id"),
            platform=data.get("platform"),
            upload_date=data.get("upload_date"),
            timestamp=data.get("timestamp"),
            scheduled_order=data.get("scheduled_order", 0),
            status=data.get("status", "pending"),
            posted_at=data.get("posted_at"),
            scheduled_time=data.get("scheduled_time"),
            scheduled_days=data.get("scheduled_days", ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]),
            retry_count=data.get("retry_count", 0),
        )


class PostQueue:
    """
    Manages the posting queue for content creator videos.

    Videos are processed in sequential order (oldest first).
    Each video gets scheduled to one of the user's daily posting times.
    Page-scoped for multi-page isolation.

    During creator mode, use disable_save() to prevent writes to the queue file,
    since all state is persisted to the session file instead.
    """

    def __init__(self, queue_file: str = "content/posting_queue.json",
                 page_id: Optional[str] = None):
        """
        Initialize the Post Queue.

        Args:
            queue_file: Path to the JSON file storing the queue
            page_id: Facebook Page ID for page-scoped queue
        """
        self.queue_file = Path(queue_file)
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        self.page_id = page_id
        self._save_enabled = True  # Controls whether _save() is called

        self.items: List[QueueItem] = []
        self.next_id = 1
        self.load()

    def disable_save(self, disabled: bool = True):
        """
        Disable automatic saving to the queue file.

        Use during creator mode where session file is the source of truth.

        Args:
            disabled: True to disable saves, False to enable
        """
        self._save_enabled = disabled

    def enable_save(self, enabled: bool = True):
        """
        Enable automatic saving to the queue file.

        Args:
            enabled: True to enable saves, False to disable
        """
        self._save_enabled = enabled

    def _should_save(self) -> bool:
        """Check if queue should save to file."""
        return self._save_enabled

    def add_video(self, video_url: str, title: str, upload_date: Optional[str] = None,
                  timestamp: Optional[float] = None, scheduled_time: Optional[str] = None,
                  source_video_id: Optional[str] = None, video_id: Optional[str] = None,
                  page_id: Optional[str] = None, session_id: Optional[str] = None,
                  platform: Optional[str] = None) -> QueueItem:
        """
        Add a video to the posting queue.

        Args:
            video_url: URL of the video
            title: Video title
            upload_date: Upload date string (YYYYMMDD)
            timestamp: Unix timestamp
            scheduled_time: When to post (HH:MM)
            source_video_id: Optional platform-specific video ID for deduplication
            video_id: Optional page-scoped video ID (generated if not provided)
            page_id: Optional Facebook Page ID for page-scoped queue (uses self.page_id if not provided)
            session_id: Optional creator session ID for session linkage
            platform: Optional platform name (youtube, tiktok, instagram)

        Returns:
            The created QueueItem
        """
        import hashlib

        # Use provided page_id or fall back to instance page_id
        item_page_id = page_id if page_id is not None else self.page_id

        # Generate a unique queue item ID (for queue entry tracking)
        # Use provided video_id as the queue item id if provided, otherwise hash from URL
        if video_id:
            item_id = video_id
        else:
            # Generate a unique queue item ID
            id_source = f"{item_page_id}:{video_url}" if item_page_id else video_url
            item_id = f"queue_{hashlib.md5(id_source.encode()).hexdigest()[:12]}"

        # Generate video_id (page-scoped video identifier) if not provided
        # video_id = page_id:platform:source_video_id hash for proper session matching
        item_video_id = video_id
        if not item_video_id and item_page_id and source_video_id and platform:
            # Generate page-scoped video_id from page_id + platform + source_video_id
            video_id_source = f"{item_page_id}:{platform}:{source_video_id}"
            item_video_id = hashlib.md5(video_id_source.encode()).hexdigest()[:16]

        # Get next sequence number
        order = self.next_id

        item = QueueItem(
            id=item_id,
            video_url=video_url,
            title=title,
            page_id=item_page_id,
            session_id=session_id,
            video_id=item_video_id,  # Page-scoped video identifier (for session matching)
            source_video_id=source_video_id,
            platform=platform,
            upload_date=upload_date,
            timestamp=timestamp,
            scheduled_order=order,
            status="pending",
            scheduled_time=scheduled_time,
        )

        self.items.append(item)
        self.next_id = order + 1

        if self._should_save():
            self._save()
        return item

    def add_multiple_videos(self, videos: List[Dict[str, Any]], scheduled_times: List[str],
                             session_id: Optional[str] = None, page_id: Optional[str] = None) -> List[QueueItem]:
        """
        Add multiple videos to the queue, distributing them across scheduled times.

        Videos are sorted by original upload timestamp (oldest first) to preserve
        the source channel's chronological order.

        Args:
            videos: List of video dicts with url, title, upload_date, timestamp
            scheduled_times: List of scheduled times (HH:MM format) in order
            session_id: Optional session ID for tracking (page-scoped)
            page_id: Optional page ID for page-scoped queue isolation

        Returns:
            List of created QueueItems in chronological order
        """
        created_items = []

        # Sort videos by upload date (oldest first)
        # Use a high sentinel value for None timestamps to push them to the end
        # This ensures videos with unknown timestamps don't appear before known-old videos
        sorted_videos = sorted(videos, key=lambda v: (v.get('timestamp') or 0) or 9999999999)

        # Debug logging for ordering verification
        import logging
        logger = logging.getLogger('creator.queue')
        logger.info(f"[ORDER] Source videos fetched: {len(sorted_videos)}, sorted by upload timestamp (oldest first)")

        if sorted_videos:
            oldest = sorted_videos[0]
            newest = sorted_videos[-1]
            logger.info(f"[ORDER] Ordering fixed: Oldest='{oldest.get('title', 'Unknown')[:50]}' (date: {oldest.get('upload_date', 'Unknown')}), Newest='{newest.get('title', 'Unknown')[:50]}'")

        # Determine how to distribute videos across time slots
        # Each time slot gets videos in chronological order
        num_times = len(scheduled_times)

        for i, video in enumerate(sorted_videos):
            # Determine which scheduled time this video should use
            time_index = i % num_times
            scheduled_time = scheduled_times[time_index]

            item = self.add_video(
                video_url=video.get('video_url', ''),
                title=video.get('title', ''),
                upload_date=video.get('upload_date'),
                timestamp=video.get('timestamp'),
                scheduled_time=scheduled_time,
                source_video_id=video.get('source_video_id'),
                platform=video.get('platform'),
                video_id=video.get('video_id'),
                session_id=session_id,
                page_id=page_id,
            )
            created_items.append(item)

        return created_items

    def get_next_pending(self, session_id: Optional[str] = None) -> Optional[QueueItem]:
        """
        Get the next pending item in the queue (by scheduled_order).

        If page_id is set on the queue, only returns items for that page.
        If session_id is provided, only returns items for that session.
        This ensures strict multi-page and multi-session isolation.

        Args:
            session_id: Optional session ID to filter by (creator mode)
        """
        if self.page_id and session_id:
            # Filter by both page_id and session_id (creator mode)
            pending = [item for item in self.items
                       if item.status == "pending"
                       and item.page_id == self.page_id
                       and item.session_id == session_id]
        elif self.page_id:
            # Filter by page_id only (non-creator mode)
            pending = [item for item in self.items
                       if item.status == "pending" and item.page_id == self.page_id]
        else:
            pending = [item for item in self.items if item.status == "pending"]
        pending.sort(key=lambda x: x.scheduled_order)
        return pending[0] if pending else None

    def get_pending_items(self, session_id: Optional[str] = None) -> List[QueueItem]:
        """
        Get all pending items sorted by order.

        If page_id is set on the queue, only returns items for that page.
        If session_id is provided, only returns items for that session.
        This ensures strict multi-page and multi-session isolation.

        Args:
            session_id: Optional session ID to filter by (creator mode)
        """
        if self.page_id and session_id:
            # Filter by both page_id and session_id (creator mode)
            pending = [item for item in self.items
                       if item.status == "pending"
                       and item.page_id == self.page_id
                       and item.session_id == session_id]
        elif self.page_id:
            # Filter by page_id only (non-creator mode)
            pending = [item for item in self.items
                       if item.status == "pending" and item.page_id == self.page_id]
        else:
            pending = [item for item in self.items if item.status == "pending"]
        pending.sort(key=lambda x: x.scheduled_order)
        return pending

    def mark_as_posted(self, item_id: str, content_id: Optional[str] = None):
        """Mark an item as posted."""
        for item in self.items:
            if item.id == item_id:
                item.status = "posted"
                item.posted_at = datetime.now().isoformat()
                if self._should_save():
                    self._save()
                return True
        return False

    def mark_as_failed(self, item_id: str, error: str = ""):
        """Mark an item as failed and increment retry count."""
        for item in self.items:
            if item.id == item_id:
                item.status = "failed"
                item.retry_count += 1
                if item.retry_count < 3:
                    item.status = "pending"  # Will retry
                if self._should_save():
                    self._save()
                return True
        return False

    def mark_as_downloading(self, item_id: str):
        """Mark an item as being downloaded."""
        for item in self.items:
            if item.id == item_id:
                item.status = "downloading"
                if self._should_save():
                    self._save()
                return True
        return False

    def mark_as_ready(self, item_id: str, content_id: str):
        """Mark an item as ready for posting (after download)."""
        for item in self.items:
            if item.id == item_id:
                item.status = "pending"  # Ready to post
                return True
        return False

    def contains_video_by_source(self, source_video_id: Optional[str], platform: Optional[str], page_id: Optional[str] = None) -> bool:
        """
        Check if a video with the given source_video_id and platform already exists in the queue.

        This prevents duplicate queue entries when resuming sessions or re-syncing content.

        Args:
            source_video_id: Platform-specific video ID
            platform: Platform name (youtube, tiktok, instagram)
            page_id: Optional page ID for page-scoped check

        Returns:
            True if video already exists in queue, False otherwise
        """
        if not source_video_id or not platform:
            return False

        for item in self.items:
            if item.source_video_id == source_video_id and item.platform == platform:
                # If page_id is specified, ensure it matches
                if page_id is None or item.page_id == page_id:
                    return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        total = len(self.items)
        pending = sum(1 for item in self.items if item.status == "pending")
        downloading = sum(1 for item in self.items if item.status == "downloading")
        posted = sum(1 for item in self.items if item.status == "posted")
        failed = sum(1 for item in self.items if item.status == "failed")

        return {
            "total": total,
            "pending": pending,
            "downloading": downloading,
            "posted": posted,
            "failed": failed,
        }

    def clear(self, reset_order: bool = True):
        """Clear all items from the queue."""
        self.items = []
        if reset_order:
            self.next_id = 1
        if self._should_save():
            self._save()

    def reset(self):
        """Reset all items to pending status."""
        for item in self.items:
            if item.status not in ("posted", "failed"):
                item.status = "pending"
        if self._should_save():
            self._save()

    def load(self) -> bool:
        """Load queue from JSON file with page-scoped filtering."""
        if not self.queue_file.exists():
            return True

        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Filter items by page_id if page_id is set
            # This ensures strict multi-page isolation
            all_items = [QueueItem.from_dict(item) for item in data.get('items', [])]
            if self.page_id:
                # Filter to only items for this page
                self.items = [item for item in all_items if item.page_id == self.page_id]
            else:
                # No page_id - load all items (backward compatibility)
                self.items = all_items

            self.next_id = data.get('next_id', max([item.scheduled_order for item in self.items], default=0) + 1)

            return True
        except Exception as e:
            console.print(f"[error]{ICONS['x']} Failed to load queue: {e}[/error]")
            return False

    def _save(self):
        """Save queue to JSON file if saves are enabled."""
        if not self._save_enabled:
            return  # Skip saving during creator mode - session is the source of truth

        data = {
            "next_id": self.next_id,
            "items": [item.to_dict() for item in self.items],
            "stats": self.get_stats(),
            "last_updated": datetime.now().isoformat(),
        }

        with open(self.queue_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def print_summary(self, creator_name: str = "Content Creator"):
        """Print a summary of the posting queue."""
        stats = self.get_stats()

        console.print()
        console.print(Panel(
            Text.assemble(
                (f"{ICONS['calendar']} Posting Queue: {creator_name}\n", "cyan"),
                (f"\nTotal Videos: {stats['total']}\n", "green"),
                (f"Pending:   {stats['pending']}  ", "yellow"),
                (f"Posted:    {stats['posted']}  ", "green"),
                (f"Failed:    {stats['failed']}", "red"),
            ),
            border_style="cyan",
            expand=False
        ))

        if not self.items:
            console.print("[info]Queue is empty.[/info]")
            return

        # Print queue table
        table = Table(show_header=True, header_style="cyan")
        table.add_column("Order", style="width=6")
        table.add_column("Status", style="width=10")
        table.add_column("Time", style="width=8")
        table.add_column("Title", min_width=40)

        for item in sorted(self.items, key=lambda x: x.scheduled_order):
            status_icon = "✓" if item.status == "posted" else ("⏳" if item.status == "downloading" else ("○" if item.status == "pending" else "✗"))
            time_str = item.scheduled_time or "Auto"

            table.add_row(
                str(item.scheduled_order),
                f"{status_icon} {item.status}",
                time_str,
                item.title[:50] + "..." if len(item.title) > 50 else item.title
            )

        console.print(table)
        console.print()