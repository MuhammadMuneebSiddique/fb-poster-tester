"""
Creator Session Module
Manages persistent creator posting sessions with page isolation.

This module provides crash-resilient session management for the creator posting workflow.
All session state is persisted to disk and survives process crashes, restarts, and system reboots.
"""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid


class SessionStatus(Enum):
    """Session status enumeration."""
    SETUP = "setup"       # Session just created, videos not yet extracted
    ACTIVE = "active"     # Session is actively posting videos
    PAUSED = "paused"     # Session temporarily paused
    COMPLETED = "completed"  # All videos successfully posted
    FAILED = "failed"     # Session encountered a fatal error


class VideoStatus(Enum):
    """Per-video status enumeration for crash recovery."""
    PENDING = "pending"     # Video is in queue, not started
    PROCESSING = "processing" # Video is being downloaded/posted (CRASH STATE)
    POSTED = "posted"       # Video successfully posted
    FAILED = "failed"       # Video posting failed after all retries


@dataclass
class SessionVideo:
    """
    Represents a video in the creator session with page-scoped identity.

    CRITICAL: Each video is uniquely identified by video_id which is page-scoped
    (page_id + platform + source_video_id hash) to prevent cross-page duplicate issues.
    """
    video_id: str           # Canonical identifier: hash of page_id + platform + source_video_id
    video_url: str          # Original video URL
    title: str
    session_id: Optional[str] = None  # Creator session this video belongs to
    upload_date: Optional[str] = None
    timestamp: Optional[float] = None
    platform: str = ""      # youtube, tiktok, instagram
    status: VideoStatus = VideoStatus.PENDING
    content_id: Optional[str] = None  # Set after download to content manager
    posted_at: Optional[str] = None
    download_attempts: int = 0
    retry_count: int = 0
    error_message: str = ""
    source_video_id: Optional[str] = None  # Platform-specific ID
    last_update_time: Optional[str] = None  # Last time this video's state was updated
    scheduled_time: Optional[str] = None  # HH:MM format for when to post
    scheduled_days: List[str] = field(default_factory=lambda: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"])  # Days to post

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "video_id": self.video_id,
            "video_url": self.video_url,
            "title": self.title,
            "session_id": self.session_id,
            "upload_date": self.upload_date,
            "timestamp": self.timestamp,
            "platform": self.platform,
            "status": self.status.value,
            "content_id": self.content_id,
            "posted_at": self.posted_at,
            "download_attempts": self.download_attempts,
            "retry_count": self.retry_count,
            "error_message": self.error_message,
            "source_video_id": self.source_video_id,
            "last_update_time": self.last_update_time,
            "scheduled_time": self.scheduled_time,
            "scheduled_days": self.scheduled_days,
        }

    def to_queue_item_dict(self) -> Dict[str, Any]:
        """Convert to QueueItem-compatible dictionary format."""
        return {
            "id": self.video_id,  # Use video_id as the queue id
            "video_url": self.video_url,
            "title": self.title,
            "page_id": self.session_id[:20] if self.session_id else None,  # Will be set by page_id
            "session_id": self.session_id,
            "source_video_id": self.source_video_id,
            "platform": self.platform,
            "upload_date": self.upload_date,
            "timestamp": self.timestamp,
            "scheduled_order": 0,  # Will be recalculated
            "status": self.status.value,
            "posted_at": self.posted_at,
            "scheduled_time": self.scheduled_time,
            "scheduled_days": self.scheduled_days,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_queue_item_dict(cls, data: Dict[str, Any], session_id: Optional[str] = None) -> 'SessionVideo':
        """Create SessionVideo from QueueItem dictionary format."""
        status_str = data.get("status", "pending")
        try:
            status = VideoStatus(status_str)
        except ValueError:
            status = VideoStatus.PENDING

        return cls(
            video_id=data.get("id", ""),
            video_url=data.get("video_url", ""),
            title=data.get("title", ""),
            session_id=data.get("session_id") or session_id,
            upload_date=data.get("upload_date"),
            timestamp=data.get("timestamp"),
            platform=data.get("platform", ""),
            status=status,
            content_id=data.get("content_id"),
            posted_at=data.get("posted_at"),
            download_attempts=data.get("download_attempts", 0),
            retry_count=data.get("retry_count", 0),
            error_message=data.get("error_message", ""),
            source_video_id=data.get("source_video_id"),
            last_update_time=data.get("last_update_time"),
            scheduled_time=data.get("scheduled_time"),
            scheduled_days=data.get("scheduled_days", ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionVideo':
        """Create from dictionary."""
        status_str = data.get("status", "pending")
        try:
            status = VideoStatus(status_str)
        except ValueError:
            status = VideoStatus.PENDING

        return cls(
            video_id=data.get("video_id", ""),
            video_url=data.get("video_url", ""),
            title=data.get("title", ""),
            session_id=data.get("session_id"),
            upload_date=data.get("upload_date"),
            timestamp=data.get("timestamp"),
            platform=data.get("platform", ""),
            status=status,
            content_id=data.get("content_id"),
            posted_at=data.get("posted_at"),
            download_attempts=data.get("download_attempts", 0),
            retry_count=data.get("retry_count", 0),
            error_message=data.get("error_message", ""),
            source_video_id=data.get("source_video_id"),
            last_update_time=data.get("last_update_time"),
            scheduled_time=data.get("scheduled_time"),
            scheduled_days=data.get("scheduled_days", ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]),
        )


@dataclass
class CreatorSession:
    """
    Persistent creator session belonging to a specific Facebook Page.

    CRITICAL: All session data is page-scoped for multi-page isolation.
    Each Facebook Page has its own session file, preventing cross-page contamination.
    """
    page_id: str                      # Page this session belongs to (CRITICAL)
    page_name: str = ""               # Name of the Facebook Page
    platform: str = ""                # youtube, tiktok, instagram
    creator_url: str = ""             # Original creator profile URL
    session_id: str = ""              # Unique session identifier
    creator_name: str = ""            # Extracted creator name
    status: SessionStatus = SessionStatus.SETUP
    videos: List[SessionVideo] = field(default_factory=list)
    current_progress: int = 0         # Index of currently processing video
    posting_schedule: List[str] = field(default_factory=list)  # HH:MM times
    queue_order: List[str] = field(default_factory=list)  # video_ids in order
    posted_videos: List[str] = field(default_factory=list)  # IDs of posted videos
    failed_videos: List[str] = field(default_factory=list)  # IDs of failed videos
    last_update_time: Optional[str] = None
    session_created_time: Optional[str] = None
    last_post_time: Optional[str] = None
    resume_point: int = 0             # Where to resume after crash
    total_videos: int = 0
    timezone: str = "Asia/Karachi"    # Default posting timezone

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "page_id": self.page_id,
            "page_name": self.page_name,
            "platform": self.platform,
            "creator_url": self.creator_url,
            "session_id": self.session_id,
            "creator_name": self.creator_name,
            "status": self.status.value,
            "videos": [v.to_dict() for v in self.videos],
            "current_progress": self.current_progress,
            "posting_schedule": self.posting_schedule,
            "queue_order": self.queue_order,
            "posted_videos": self.posted_videos,
            "failed_videos": self.failed_videos,
            "last_update_time": self.last_update_time,
            "session_created_time": self.session_created_time,
            "last_post_time": self.last_post_time,
            "resume_point": self.resume_point,
            "total_videos": self.total_videos,
            "timezone": self.timezone,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CreatorSession':
        """Create from dictionary."""
        status_str = data.get("status", "setup")
        try:
            status = SessionStatus(status_str)
        except ValueError:
            status = SessionStatus.SETUP

        session = cls(
            page_id=data.get("page_id", ""),
            page_name=data.get("page_name", ""),
            platform=data.get("platform", ""),
            creator_url=data.get("creator_url", ""),
            session_id=data.get("session_id", ""),
            creator_name=data.get("creator_name", ""),
            status=status,
            current_progress=data.get("current_progress", 0),
            posting_schedule=data.get("posting_schedule", []),
            queue_order=data.get("queue_order", []),
            posted_videos=data.get("posted_videos", []),
            failed_videos=data.get("failed_videos", []),
            last_update_time=data.get("last_update_time"),
            session_created_time=data.get("session_created_time"),
            last_post_time=data.get("last_post_time"),
            resume_point=data.get("resume_point", 0),
            total_videos=data.get("total_videos", 0),
            timezone=data.get("timezone", "Asia/Karachi"),
        )
        # Load videos
        session.videos = [SessionVideo.from_dict(v) for v in data.get("videos", [])]
        return session

    def get_posted_count(self) -> int:
        """Get count of successfully posted videos."""
        return sum(1 for v in self.videos if v.status == VideoStatus.POSTED)

    def get_pending_count(self) -> int:
        """Get count of pending videos."""
        return sum(1 for v in self.videos if v.status == VideoStatus.PENDING)

    def get_processing_count(self) -> int:
        """Get count of videos currently being processed (crash state)."""
        return sum(1 for v in self.videos if v.status == VideoStatus.PROCESSING)

    def get_failed_count(self) -> int:
        """Get count of failed videos."""
        return sum(1 for v in self.videos if v.status == VideoStatus.FAILED)

    def get_next_pending_video(self) -> Optional[SessionVideo]:
        """Get the next pending video in queue order."""
        pending = [v for v in self.videos if v.status == VideoStatus.PENDING]
        pending.sort(key=lambda v: self.queue_order.index(v.video_id) if v.video_id in self.queue_order else len(self.queue_order))
        return pending[0] if pending else None

    def get_video_by_id(self, video_id: str) -> Optional[SessionVideo]:
        """Get video by its stable video_id."""
        for video in self.videos:
            if video.video_id == video_id:
                return video
        return None

    def get_video_by_source_id(self, source_video_id: str, platform: str = "") -> Optional[SessionVideo]:
        """Get video by source_video_id (platform-specific video ID like YouTube video ID)."""
        for video in self.videos:
            if video.source_video_id == source_video_id:
                # Optionally filter by platform if provided
                if platform and video.platform != platform:
                    continue
                return video
        return None

    def get_video_by_url(self, video_url: str, platform: str = "") -> Optional[SessionVideo]:
        """Get video by its video_url with optional platform filter."""
        for video in self.videos:
            if video.video_url == video_url:
                # Optionally filter by platform if provided
                if platform and video.platform != platform:
                    continue
                return video
        return None


class SessionManager:
    """
    Manages persistent creator sessions with page isolation.

    CRITICAL: All operations are scoped to a specific Facebook Page ID.
    This ensures complete isolation between different Facebook Pages.

    Session file: sessions/page_<page_id>.json
    This single file contains ALL creator posting state for the page.
    """

    def __init__(self, page_id: str, session_dir: str = "sessions"):
        """
        Initialize the Session Manager for a specific page.

        Args:
            page_id: The Facebook Page ID this session belongs to
            session_dir: Directory to store session files
        """
        self.page_id = page_id
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        # New unified session file: one per page, contains all creator posting state
        self.session_file = self.session_dir / f"page_{page_id}.json"

    def get_session_file_path(self) -> str:
        """Get the session file path for this page."""
        return str(self.session_file)

    def load_session(self) -> Optional[CreatorSession]:
        """
        Load session from file, return None if not exists.

        Returns:
            CreatorSession if file exists and is valid, None otherwise
        """
        if not self.session_file.exists():
            return None
        try:
            with open(self.session_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return CreatorSession.from_dict(data)
        except Exception as e:
            # Corrupted file - return None so user can start fresh
            return None

    def save_session(self, session: CreatorSession) -> bool:
        """
        Save session with atomic write (temp file + rename).

        Atomic writes ensure crash safety - if process crashes during write,
        the original file remains intact.

        Args:
            session: The session to save

        Returns:
            True if saved successfully, False otherwise
        """
        import logging
        logger = logging.getLogger('creator.session')

        try:
            # Mark the save in progress
            session.last_update_time = datetime.now().isoformat()

            logger.info(f"[SESSION] Saving session {session.session_id} for page {session.page_id}: {len(session.videos)} videos, status={session.status.value}")

            # Write to temp file first (atomic write pattern)
            temp_file = self.session_file.with_suffix('.tmp')

            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(session.to_dict(), f, indent=2, ensure_ascii=False)

            # Atomic rename (works on Windows and POSIX)
            os.replace(str(temp_file), str(self.session_file))
            logger.info(f"[SESSION] Session saved to {self.session_file}")
            return True
        except Exception as e:
            logger.error(f"[SESSION] Failed to save session: {e}")
            # Clean up temp file on failure
            temp_file = self.session_file.with_suffix('.tmp')
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except:
                    pass
            return False

    def has_incomplete_session(self) -> bool:
        """
        Check if there's an incomplete session (processing or active).

        Incomplete sessions need recovery on restart.

        Returns:
            True if there's an incomplete session, False otherwise
        """
        session = self.load_session()
        if not session:
            return False
        # SETUP means videos were extracted but none posted yet
        # ACTIVE means currently posting
        result = session.status in (SessionStatus.ACTIVE, SessionStatus.SETUP)
        if result:
            import logging
            logger = logging.getLogger('creator.session')
            logger.info(f"[SESSION] has_incomplete_session()=True for page {self.page_id}, status={session.status.value}, videos={len(session.videos)}")
        return result

    def get_incomplete_session(self) -> Optional[CreatorSession]:
        """
        Get incomplete session for recovery.

        Returns:
            CreatorSession if incomplete session exists, None otherwise
        """
        session = self.load_session()
        if session and session.status in (SessionStatus.ACTIVE, SessionStatus.SETUP):
            return session
        return None

    def create_new_session(self, creator_url: str, creator_name: str,
                           platform: str, page_id: str) -> CreatorSession:
        """
        Create a new session.

        Args:
            creator_url: URL of the creator's profile
            creator_name: Display name of the creator
            platform: The platform (youtube, tiktok, instagram)
            page_id: The Facebook Page ID

        Returns:
            A new CreatorSession instance (not yet saved)
        """
        session = CreatorSession(
            page_id=page_id,
            platform=platform,
            creator_url=creator_url,
            session_id=str(uuid.uuid4())[:12],
            creator_name=creator_name,
            status=SessionStatus.SETUP,
            session_created_time=datetime.now().isoformat(),
            last_update_time=datetime.now().isoformat(),
        )
        return session

    def delete_session(self) -> bool:
        """
        Delete session file.

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            if self.session_file.exists():
                self.session_file.unlink()
            return True
        except Exception:
            return False

    def update_video_status(self, video_id: str, status: VideoStatus,
                            save: bool = True) -> bool:
        """
        Update a video's status in the session.

        Args:
            video_id: The video ID to update
            status: The new status
            save: Whether to save the session immediately

        Returns:
            True if successful, False if video not found
        """
        session = self.load_session()
        if not session:
            return False

        video = session.get_video_by_id(video_id)
        if not video:
            return False

        video.status = status
        video.last_update_time = datetime.now().isoformat()

        if save:
            return self.save_session(session)
        return True

    def mark_video_processing(self, video_id: str) -> bool:
        """Mark a video as processing (being downloaded/posted)."""
        session = self.load_session()
        if not session:
            return False

        video = session.get_video_by_id(video_id)
        if not video:
            return False

        video.status = VideoStatus.PROCESSING
        video.download_attempts += 1
        video.last_update_time = datetime.now().isoformat()
        return self.save_session(session)

    def mark_video_posted(self, video_id: str, content_id: str = None) -> bool:
        """Mark a video as successfully posted."""
        session = self.load_session()
        if not session:
            return False

        video = session.get_video_by_id(video_id)
        if not video:
            return False

        video.status = VideoStatus.POSTED
        video.content_id = content_id
        video.posted_at = datetime.now().isoformat()
        video.last_update_time = video.posted_at

        # Update session-level tracking
        if video.video_id not in session.posted_videos:
            session.posted_videos.append(video.video_id)
        session.current_progress = len(session.posted_videos) + session.get_pending_count() + session.get_processing_count() + session.get_failed_count()
        session.resume_point = session.current_progress
        session.last_post_time = video.posted_at

        return self.save_session(session)

    def mark_video_failed(self, video_id: str, error_message: str = "") -> bool:
        """Mark a video as failed."""
        session = self.load_session()
        if not session:
            return False

        video = session.get_video_by_id(video_id)
        if not video:
            return False

        video.status = VideoStatus.FAILED
        video.error_message = error_message

        # Update session-level tracking
        if video.video_id not in session.failed_videos:
            session.failed_videos.append(video.video_id)
        session.current_progress = len(session.posted_videos) + session.get_pending_count() + session.get_processing_count() + session.get_failed_count()
        session.resume_point = session.current_progress
        session.last_update_time = datetime.now().isoformat()

        return self.save_session(session)

    def mark_video_posted_by_source(self, source_video_id: str, content_id: str = None, platform: str = "") -> bool:
        """Mark a video as posted by source_video_id."""
        import logging
        logger = logging.getLogger('creator.session')

        session = self.load_session()
        if not session:
            logger.warning(f"[SESSION] mark_video_posted_by_source: Could not load session")
            return False

        video = session.get_video_by_source_id(source_video_id, platform)
        if not video:
            logger.warning(f"[SESSION] mark_video_posted_by_source: Video not found for source_id={source_video_id}, platform={platform}")
            return False

        video.status = VideoStatus.POSTED
        video.content_id = content_id
        video.posted_at = datetime.now().isoformat()
        video.last_update_time = video.posted_at

        # Update session-level tracking
        if video.video_id not in session.posted_videos:
            session.posted_videos.append(video.video_id)
        session.current_progress = len(session.posted_videos) + session.get_pending_count() + session.get_processing_count() + session.get_failed_count()
        session.resume_point = session.current_progress
        session.last_post_time = video.posted_at

        result = self.save_session(session)
        if result:
            logger.info(f"[SESSION] Video {video.video_id} marked POSTED - Saving session: {session.total_videos} total, {len(session.posted_videos)} posted, {session.get_pending_count()} pending")
            logger.info(f"[SESSION] Session state persisted successfully")
        return result

    def mark_video_failed_by_source(self, source_video_id: str, error_message: str = "", platform: str = "") -> bool:
        """Mark a video as failed by source_video_id."""
        import logging
        logger = logging.getLogger('creator.session')

        session = self.load_session()
        if not session:
            logger.warning(f"[SESSION] mark_video_failed_by_source: Could not load session")
            return False

        video = session.get_video_by_source_id(source_video_id, platform)
        if not video:
            logger.warning(f"[SESSION] mark_video_failed_by_source: Video not found for source_id={source_video_id}, platform={platform}")
            return False

        video.status = VideoStatus.FAILED
        video.error_message = error_message
        video.last_update_time = datetime.now().isoformat()

        # Update session-level tracking
        if video.video_id not in session.failed_videos:
            session.failed_videos.append(video.video_id)
        session.current_progress = len(session.posted_videos) + session.get_pending_count() + session.get_processing_count() + session.get_failed_count()
        session.resume_point = session.current_progress

        result = self.save_session(session)
        if result:
            logger.info(f"[SESSION] Video {video.video_id} marked FAILED - Saving session: {session.total_videos} total, {len(session.posted_videos)} posted, {session.get_pending_count()} pending, {len(session.failed_videos)} failed")
            logger.info(f"[SESSION] Session state persisted successfully")
        return result

    def mark_video_pending_by_url(self, video_url: str, platform: str = "", reset_retry: bool = True) -> bool:
        """
        Reset a video to pending status for retry by its video URL.

        Args:
            video_url: The video URL to find
            platform: Platform name (youtube, tiktok, instagram)
            reset_retry: If True, reset retry counters (for starting fresh).
                        If False, keep retry counters (for retry recovery).
        """
        import logging
        logger = logging.getLogger('creator.session')

        session = self.load_session()
        if not session:
            logger.warning(f"[SESSION] mark_video_pending_by_url: Could not load session")
            return False

        video = session.get_video_by_url(video_url, platform)
        if not video:
            logger.warning(f"[SESSION] mark_video_pending_by_url: Video not found for url={video_url}, platform={platform}")
            return False

        video.status = VideoStatus.PENDING
        if reset_retry:
            video.retry_count = 0
            video.error_message = ""
        video.download_attempts = 0
        video.last_update_time = datetime.now().isoformat()
        video.posted_at = None
        video.content_id = None

        # Remove from failed_videos if it was added there
        if video.video_id in session.failed_videos:
            session.failed_videos.remove(video.video_id)

        result = self.save_session(session)
        if result:
            logger.info(f"[SESSION] Video {video.video_id} marked PENDING for retry - Saving session: {session.total_videos} total, {len(session.posted_videos)} posted, {session.get_pending_count()} pending, {len(session.failed_videos)} failed")
            logger.info(f"[SESSION] Session state persisted successfully")
        return result

    def increment_download_attempt(self, video_id: str, increment_retry: bool = True) -> bool:
        """
        Increment download attempt counter for a video.

        Args:
            video_id: The video ID to update
            increment_retry: If True, increment retry_count as well

        Returns:
            True if successful
        """
        session = self.load_session()
        if not session:
            return False

        video = session.get_video_by_id(video_id)
        if not video:
            return False

        video.download_attempts += 1
        if increment_retry:
            video.retry_count += 1
        video.last_update_time = datetime.now().isoformat()

        return self.save_session(session)

    def add_video_to_session(self, video: SessionVideo,
                             position: int = None) -> bool:
        """
        Add a new video to the session.

        Args:
            video: The video to add
            position: Optional position in queue (default: append)

        Returns:
            True if successful
        """
        import logging
        logger = logging.getLogger('creator.session')

        session = self.load_session()
        if not session:
            logger.warning(f"[SESSION] add_video_to_session: No session loaded from file!")
            return False

        # Update queue order
        video_id = video.video_id
        if video_id not in session.queue_order:
            session.queue_order.append(video_id)

        # Check for duplicates
        if video.video_id in [v.video_id for v in session.videos]:
            logger.info(f"[SESSION] Video {video.video_id} already in session")
            return False

        if position is not None and 0 <= position <= len(session.videos):
            session.videos.insert(position, video)
        else:
            session.videos.append(video)
            position = len(session.videos) - 1

        logger.info(f"[SESSION] Added video {video_id} to session, total videos now: {len(session.videos)}")

        result = self.save_session(session)
        return result

    def generate_video_id(self, platform: str, source_video_id: str) -> str:
        """
        Generate a stable page-scoped video ID.

        This ensures the same video posted to different pages has different IDs,
        preventing cross-page duplicate issues.

        Args:
            platform: The platform (youtube, tiktok, instagram)
            source_video_id: The platform's video ID

        Returns:
            A stable, page-scoped video ID
        """
        import hashlib
        # Create a unique identifier that includes page_id, platform, and source ID
        unique_str = f"{self.page_id}:{platform}:{source_video_id}"
        hash_obj = hashlib.md5(unique_str.encode())
        return f"{platform}_{hash_obj.hexdigest()[:16]}"

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get session statistics for display.

        Returns:
            Dictionary with posting statistics
        """
        session = self.load_session()
        if not session:
            return {
                "total_videos": 0,
                "posted": 0,
                "pending": 0,
                "processing": 0,
                "failed": 0,
            }

        return {
            "total_videos": len(session.videos),
            "posted": session.get_posted_count(),
            "pending": session.get_pending_count(),
            "processing": session.get_processing_count(),
            "failed": session.get_failed_count(),
        }


def create_video_id_for_page(page_id: str, platform: str, source_video_id: str) -> str:
    """
    Convenience function to generate a page-scoped video ID.

    Args:
        page_id: Facebook Page ID
        platform: Platform name (youtube, tiktok, instagram)
        source_video_id: Platform-specific video ID

    Returns:
        Stable page-scoped video ID
    """
    import hashlib
    unique_str = f"{page_id}:{platform}:{source_video_id}"
    hash_obj = hashlib.md5(unique_str.encode())
    return f"{platform}_{hash_obj.hexdigest()[:16]}"


def clear_session(page_id: str, session_dir: str = "sessions") -> bool:
    """
    Clear (delete) all sessions for a page.

    Used when starting fresh or during cleanup.

    Args:
        page_id: The Facebook Page ID
        session_dir: Session directory path

    Returns:
        True if cleared successfully
    """
    manager = SessionManager(page_id, session_dir)
    return manager.delete_session()