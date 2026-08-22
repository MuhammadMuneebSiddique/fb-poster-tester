"""
Content Manager Module
Handles loading and managing content from the content directory.
"""

import os
import json
import hashlib
import random
import mimetypes
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import logging


class ContentType(Enum):
    """Types of content that can be posted."""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    LINK = "link"


@dataclass
class ContentItem:
    """Represents a piece of content to post."""
    id: str
    title: str
    type: ContentType
    path: Path
    message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    file_size: int = 0
    mime_type: str = ""
    post_count: int = 0
    last_posted: Optional[str] = None
    used_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "title": self.title,
            "type": self.type.value,
            "path": str(self.path),
            "message": self.message,
            "metadata": self.metadata,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "post_count": self.post_count,
            "last_posted": self.last_posted,
            "used_count": self.used_count
        }


class ContentManager:
    """
    Manages content loading from the content directory.

    Supports text, image, video, and link content with metadata files.
    """

    def __init__(
        self,
        config: Dict[str, Any],
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the Content Manager.

        Args:
            config: Configuration dictionary
            logger: Logger instance
        """
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

        # Configuration
        self.content_folder = Path(config.get("content_folder", "content"))
        self.shuffle = config.get("shuffle_content", True)
        self.recycle = config.get("recycle_content", True)

        # Supported extensions
        self.image_extensions = set(config.get("image_extensions", ["jpg", "jpeg", "png", "gif", "webp"]))
        self.video_extensions = set(config.get("video_extensions", ["mp4", "mov", "avi", "mkv", "webm"]))

        # Size limits
        self.max_image_size = config.get("max_image_size_mb", 50) * 1024 * 1024
        self.max_video_size = config.get("max_video_size_mb", 500) * 1024 * 1024

        # Default text
        self.default_text = config.get("default_text", "Check out our latest update! 🚀")
        self.default_hashtags = config.get("default_hashtags", "#facebook #socialmedia #automation")

        # Content storage
        self.content_items: Dict[str, ContentItem] = {}
        self.content_by_type: Dict[ContentType, List[str]] = {
            ContentType.TEXT: [],
            ContentType.IMAGE: [],
            ContentType.VIDEO: [],
            ContentType.LINK: []
        }
        self.current_index: Dict[ContentType, int] = {
            ContentType.TEXT: 0,
            ContentType.IMAGE: 0,
            ContentType.VIDEO: 0,
            ContentType.LINK: 0
        }
        self.usage_history: List[str] = []

        # Load content
        self.load_content()

    def load_content(self) -> int:
        """
        Load content from the content directory.

        Returns:
            Number of content items loaded
        """
        self.content_items.clear()
        for ctype in self.content_by_type:
            self.content_by_type[ctype].clear()
        self.current_index = {ctype: 0 for ctype in ContentType}
        self.usage_history.clear()

        if not self.content_folder.exists():
            self.logger.warning(f"Content folder does not exist: {self.content_folder}")
            self.content_folder.mkdir(parents=True, exist_ok=True)
            self._create_sample_content()
            return 0

        self.logger.info(f"Loading content from: {self.content_folder}")

        # Scan all subdirectories
        for subdir in self.content_folder.iterdir():
            if not subdir.is_dir():
                continue

            content_type = self._get_content_type_from_dir(subdir)
            if not content_type:
                continue

            for file_path in subdir.iterdir():
                if file_path.is_file() and not file_path.name.startswith('.'):
                    # Skip metadata files
                    if file_path.suffix in ['.meta', '.json']:
                        continue

                    self._process_file(file_path, content_type)

        # Shuffle if configured
        if self.shuffle:
            for ctype in self.content_by_type:
                random.shuffle(self.content_by_type[ctype])

        total = len(self.content_items)
        self.logger.info(f"Loaded {total} content items:")
        for ctype, items in self.content_by_type.items():
            self.logger.info(f"  {ctype.value}: {len(items)}")

        return total

    def _get_content_type_from_dir(self, dir_path: Path) -> Optional[ContentType]:
        """Determine content type from directory name."""
        dir_name = dir_path.name.lower()
        if dir_name in ['text', 'texts', 'txt']:
            return ContentType.TEXT
        elif dir_name in ['image', 'images', 'img', 'photo', 'photos', 'picture', 'pictures']:
            return ContentType.IMAGE
        elif dir_name in ['video', 'videos', 'vid', 'movie', 'movies']:
            return ContentType.VIDEO
        elif dir_name in ['link', 'links', 'url', 'urls']:
            return ContentType.LINK
        return None

    def _process_file(self, file_path: Path, content_type: ContentType):
        """Process a content file."""
        try:
            # Check file size
            file_size = file_path.stat().st_size

            if content_type == ContentType.IMAGE and file_size > self.max_image_size:
                self.logger.warning(f"Image too large, skipping: {file_path} ({file_size} bytes)")
                return
            elif content_type == ContentType.VIDEO and file_size > self.max_video_size:
                self.logger.warning(f"Video too large, skipping: {file_path} ({file_size} bytes)")
                return

            # Load metadata if exists
            metadata = self._load_metadata(file_path)

            # Generate content ID
            relative_path = file_path.relative_to(self.content_folder)
            content_id = hashlib.md5(str(relative_path).encode()).hexdigest()[:12]

            # Get title
            title = metadata.get('title', file_path.stem)

            # Get message
            message = metadata.get('message', '')
            if not message and content_type == ContentType.TEXT:
                # For text files, use file content as message
                try:
                    message = file_path.read_text(encoding='utf-8').strip()
                except Exception:
                    message = self.default_text

            # Get MIME type
            mime_type, _ = mimetypes.guess_type(str(file_path))
            mime_type = mime_type or ''

            # Create content item
            item = ContentItem(
                id=content_id,
                title=title,
                type=content_type,
                path=file_path,
                message=message,
                metadata=metadata,
                file_size=file_size,
                mime_type=mime_type
            )

            self.content_items[content_id] = item
            self.content_by_type[content_type].append(content_id)

            self.logger.debug(f"Loaded content: {content_id} - {title} ({content_type.value})")

        except Exception as e:
            self.logger.error(f"Failed to process file {file_path}: {e}")

    def _load_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Load metadata from .meta.json file."""
        meta_path = file_path.with_suffix(file_path.suffix + '.meta.json')
        if not meta_path.exists():
            meta_path = file_path.parent / f"{file_path.stem}.meta.json"

        if meta_path.exists():
            try:
                with open(meta_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"Failed to load metadata from {meta_path}: {e}")

        return {}

    def _create_sample_content(self):
        """Create sample content structure and files."""
        self.logger.info("Creating sample content structure...")

        # Create directories
        dirs = {
            ContentType.TEXT: self.content_folder / 'text',
            ContentType.IMAGE: self.content_folder / 'images',
            ContentType.VIDEO: self.content_folder / 'videos',
            ContentType.LINK: self.content_folder / 'links'
        }

        for ctype, dir_path in dirs.items():
            dir_path.mkdir(parents=True, exist_ok=True)

        # Create sample text content
        sample_texts = [
            ("Motivation Monday", "Start your week with purpose! 💪\n\nEvery small step counts towards your goals. Keep pushing forward!\n\n#motivation #monday #success"),
            ("Tech Tip Tuesday", "Quick tip: Use keyboard shortcuts to boost your productivity! ⌨️\n\nCtrl+C/V for copy/paste\nCtrl+Z for undo\nWin+D for desktop\n\n#techtips #productivity"),
            ("Weekend Vibes", "Happy Weekend! 🎉\n\nTime to relax, recharge, and enjoy some well-deserved rest.\n\n#weekend #relax #recharge")
        ]

        for i, (title, content) in enumerate(sample_texts):
            file_path = dirs[ContentType.TEXT] / f"sample_{i+1}.txt"
            file_path.write_text(content, encoding='utf-8')

            # Create metadata
            meta = {"title": title, "tags": ["sample", "text"]}
            meta_path = file_path.with_suffix('.meta.json')
            meta_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')

        # Create placeholder files for images and videos
        for ctype, dir_path in dirs.items():
            if ctype == ContentType.IMAGE:
                placeholder = dir_path / "README.md"
                placeholder.write_text("# Images Folder\n\nPlace your image files here (jpg, png, gif, webp)\n\nAdd a .meta.json file for each image with title and message.", encoding='utf-8')
            elif ctype == ContentType.VIDEO:
                placeholder = dir_path / "README.md"
                placeholder.write_text("# Videos Folder\n\nPlace your video files here (mp4, mov, avi, mkv, webm)\n\nAdd a .meta.json file for each video with title and description.", encoding='utf-8')
            elif ctype == ContentType.LINK:
                placeholder = dir_path / "README.md"
                placeholder.write_text("# Links Folder\n\nCreate .json files with link information:\n```json\n{\n  \"title\": \"Article Title\",\n  \"link\": \"https://example.com\",\n  \"message\": \"Check this out!\"\n}\n```", encoding='utf-8')

        self.logger.info("Sample content structure created.")

    def get_content(self, content_id: str) -> Optional[ContentItem]:
        """Get content item by ID."""
        return self.content_items.get(content_id)

    def get_next_content(self, content_type: Optional[ContentType] = None) -> Optional[ContentItem]:
        """
        Get the next content item in rotation.

        Args:
            content_type: Specific type to get, or None for any type

        Returns:
            Next ContentItem or None if no content available
        """
        if content_type:
            return self._get_next_of_type(content_type)

        # Try types in order: VIDEO, IMAGE, TEXT, LINK
        for ctype in [ContentType.VIDEO, ContentType.IMAGE, ContentType.TEXT, ContentType.LINK]:
            item = self._get_next_of_type(ctype)
            if item:
                return item

        return None

    def _get_next_of_type(self, content_type: ContentType) -> Optional[ContentItem]:
        """Get next item of specific type."""
        items = self.content_by_type.get(content_type, [])
        if not items:
            return None

        index = self.current_index[content_type]
        content_id = items[index]

        # Update index
        self.current_index[content_type] = (index + 1) % len(items)

        # Check if we've cycled through all items
        if self.current_index[content_type] == 0 and not self.recycle:
            return None

        return self.content_items.get(content_id)

    def get_random_content(self, content_type: Optional[ContentType] = None) -> Optional[ContentItem]:
        """Get a random content item."""
        if content_type:
            items = self.content_by_type.get(content_type, [])
        else:
            items = list(self.content_items.keys())

        if not items:
            return None

        content_id = random.choice(items)
        return self.content_items.get(content_id)

    def mark_used(self, content_id: str):
        """Mark content as used."""
        item = self.content_items.get(content_id)
        if item:
            item.used_count += 1
            item.last_posted = datetime.now().isoformat()
            self.usage_history.append(content_id)

    def list_content(self) -> List[Dict[str, Any]]:
        """List all content items."""
        return [item.to_dict() for item in self.content_items.values()]

    def list_by_type(self, content_type: ContentType) -> List[Dict[str, Any]]:
        """List content items by type."""
        return [
            self.content_items[item_id].to_dict()
            for item_id in self.content_by_type.get(content_type, [])
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Get content statistics."""
        return {
            "total_items": len(self.content_items),
            "by_type": {
                ctype.value: len(items)
                for ctype, items in self.content_by_type.items()
            },
            "total_usage": sum(item.used_count for item in self.content_items.values()),
            "content_folder": str(self.content_folder)
        }

    def add_content(
        self,
        file_path: Path,
        content_type: ContentType,
        title: Optional[str] = None,
        message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[ContentItem]:
        """
        Add new content (copies file to content directory).

        Args:
            file_path: Source file path
            content_type: Type of content
            title: Optional title
            message: Optional message/caption
            metadata: Optional metadata

        Returns:
            Created ContentItem or None
        """
        import shutil

        # Determine target directory
        type_dirs = {
            ContentType.TEXT: self.content_folder / 'text',
            ContentType.IMAGE: self.content_folder / 'images',
            ContentType.VIDEO: self.content_folder / 'videos',
            ContentType.LINK: self.content_folder / 'links'
        }
        target_dir = type_dirs.get(content_type, self.content_folder)
        target_dir.mkdir(parents=True, exist_ok=True)

        # Copy file
        target_path = target_dir / file_path.name
        if target_path.exists():
            # Add timestamp to avoid overwriting
            import time
            stem = file_path.stem
            suffix = file_path.suffix
            target_path = target_dir / f"{stem}_{int(time.time())}{suffix}"

        shutil.copy2(file_path, target_path)

        # Save metadata if provided
        if metadata or message:
            meta = metadata or {}
            if message:
                meta['message'] = message
            if title:
                meta['title'] = title

            meta_path = target_path.with_suffix(target_path.suffix + '.meta.json')
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(meta, f, indent=2)

        # Reload content
        self.load_content()

        # Return new item
        relative_path = target_path.relative_to(self.content_folder)
        content_id = hashlib.md5(str(relative_path).encode()).hexdigest()[:12]
        return self.content_items.get(content_id)