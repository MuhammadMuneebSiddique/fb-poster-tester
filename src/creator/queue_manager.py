"""
Queue Manager
Manages the posting queue for content creator videos.
"""

import os
import json
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
    """Represents an item in the posting queue."""
    id: str
    video_url: str
    title: str
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
    """

    def __init__(self, queue_file: str = "content/posting_queue.json"):
        """
        Initialize the Post Queue.

        Args:
            queue_file: Path to the JSON file storing the queue
        """
        self.queue_file = Path(queue_file)
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)

        self.items: List[QueueItem] = []
        self.next_id = 1

    def add_video(self, video_url: str, title: str, upload_date: Optional[str] = None,
                  timestamp: Optional[float] = None, scheduled_time: Optional[str] = None) -> QueueItem:
        """
        Add a video to the posting queue.

        Args:
            video_url: URL of the video
            title: Video title
            upload_date: Upload date string (YYYYMMDD)
            timestamp: Unix timestamp
            scheduled_time: When to post (HH:MM)

        Returns:
            The created QueueItem
        """
        import hashlib

        # Generate a unique ID
        item_id = f"queue_{hashlib.md5(f'{video_url}{timestamp}'.encode()).hexdigest()[:12]}"

        # Get next sequence number
        order = self.next_id

        item = QueueItem(
            id=item_id,
            video_url=video_url,
            title=title,
            upload_date=upload_date,
            timestamp=timestamp,
            scheduled_order=order,
            status="pending",
            scheduled_time=scheduled_time,
        )

        self.items.append(item)
        self.next_id = order + 1

        self._save()
        return item

    def add_multiple_videos(self, videos: List[Dict[str, Any]], scheduled_times: List[str]) -> List[QueueItem]:
        """
        Add multiple videos to the queue, distributing them across scheduled times.

        Videos are sorted by original upload timestamp (oldest first) to preserve
        the source channel's chronological order.

        Args:
            videos: List of video dicts with url, title, upload_date, timestamp
            scheduled_times: List of scheduled times (HH:MM format) in order

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
            )
            created_items.append(item)

        return created_items

    def get_next_pending(self) -> Optional[QueueItem]:
        """Get the next pending item in the queue (by scheduled_order)."""
        pending = [item for item in self.items if item.status == "pending"]
        pending.sort(key=lambda x: x.scheduled_order)
        return pending[0] if pending else None

    def get_pending_items(self) -> List[QueueItem]:
        """Get all pending items sorted by order."""
        pending = [item for item in self.items if item.status == "pending"]
        pending.sort(key=lambda x: x.scheduled_order)
        return pending

    def mark_as_posted(self, item_id: str, content_id: Optional[str] = None):
        """Mark an item as posted."""
        for item in self.items:
            if item.id == item_id:
                item.status = "posted"
                item.posted_at = datetime.now().isoformat()
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
                self._save()
                return True
        return False

    def mark_as_downloading(self, item_id: str):
        """Mark an item as being downloaded."""
        for item in self.items:
            if item.id == item_id:
                item.status = "downloading"
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
        self._save()

    def reset(self):
        """Reset all items to pending status."""
        for item in self.items:
            if item.status not in ("posted", "failed"):
                item.status = "pending"
        self._save()

    def load(self) -> bool:
        """Load queue from JSON file."""
        if not self.queue_file.exists():
            return True

        try:
            with open(self.queue_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.items = [QueueItem.from_dict(item) for item in data.get('items', [])]
            self.next_id = data.get('next_id', max([item.scheduled_order for item in self.items], default=0) + 1)

            return True
        except Exception as e:
            console.print(f"[error]{ICONS['x']} Failed to load queue: {e}[/error]")
            return False

    def _save(self):
        """Save queue to JSON file."""
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