"""
Facebook Graph API Client
Handles all communication with Facebook Graph API.
"""

import os
import logging
import time
import requests
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime
import json


class FacebookClient:
    """
    Client for interacting with Facebook Graph API.

    Supports posting text, images, videos, and links to Facebook Pages.
    """

    def __init__(
        self,
        page_id: str,
        access_token: str,
        api_version: str = "v21.0",
        timeout: int = 120,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the Facebook Graph API client.

        Args:
            page_id: Facebook Page ID
            access_token: Page Access Token with pages_manage_posts permission
            api_version: Graph API version (default: v21.0)
            timeout: Request timeout in seconds
            logger: Logger instance
        """
        self.page_id = page_id
        self.access_token = access_token
        self.api_version = api_version
        self.timeout = timeout
        self.logger = logger or logging.getLogger(__name__)

        # Base API URL
        self.base_url = f"https://graph.facebook.com/{api_version}"

        # Session for connection pooling
        self.session = requests.Session()
        self.session.params = {"access_token": access_token}
        self.session.timeout = timeout

    def test_connection(self) -> bool:
        """
        Test connection to Facebook Graph API.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            url = f"{self.base_url}/{self.page_id}"
            params = {"fields": "id,name", "access_token": self.access_token}

            response = self.session.get(url, params=params, timeout=self.timeout)

            if response.status_code == 200:
                data = response.json()
                self.logger.info(f"Connected to page: {data.get('name')} (ID: {data.get('id')})")
                return True
            else:
                self._log_error_response(response, "Connection test")
                return False

        except Exception as e:
            self.logger.error(f"Connection test error: {e}")
            return False

    def get_page_info(self) -> Optional[Dict[str, Any]]:
        """Get page information."""
        try:
            url = f"{self.base_url}/{self.page_id}"
            params = {"fields": "id,name,category,fan_count,about", "access_token": self.access_token}

            response = self.session.get(url, params=params, timeout=self.timeout)

            if response.status_code == 200:
                return response.json()
            else:
                self._log_error_response(response, "Get page info")
                return None

        except Exception as e:
            self.logger.error(f"Error getting page info: {e}")
            return None

    def post_text(
        self,
        message: str,
        published: bool = True,
        scheduled_publish_time: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Post a text message to the page.

        Args:
            message: Text message to post
            published: Whether to publish immediately (True) or save as draft (False)
            scheduled_publish_time: Unix timestamp for scheduled publishing

        Returns:
            Post response data or None on failure
        """
        try:
            url = f"{self.base_url}/{self.page_id}/feed"

            data = {
                "message": message,
                "published": "true" if published else "false"
            }

            if scheduled_publish_time and not published:
                data["scheduled_publish_time"] = str(scheduled_publish_time)
                data["published"] = "false"

            response = self.session.post(url, data=data, timeout=self.timeout)

            return self._handle_response(response, "text post")

        except Exception as e:
            self.logger.error(f"Error posting text: {e}")
            return None

    def post_image(
        self,
        image_path: str,
        message: str = "",
        published: bool = True,
        scheduled_publish_time: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Post an image to the page.

        Args:
            image_path: Path to image file
            message: Optional message to accompany image
            published: Whether to publish immediately
            scheduled_publish_time: Unix timestamp for scheduled publishing

        Returns:
            Post response data or None on failure
        """
        try:
            # Upload image first
            media_id = self._upload_photo(image_path)
            if not media_id:
                return None

            # Create post with attached media
            url = f"{self.base_url}/{self.page_id}/feed"

            data = {
                "message": message,
                "attached_media[0]": json.dumps({"media_fbid": media_id}),
                "published": "true" if published else "false"
            }

            if scheduled_publish_time and not published:
                data["scheduled_publish_time"] = str(scheduled_publish_time)
                data["published"] = "false"

            response = self.session.post(url, data=data, timeout=self.timeout)

            return self._handle_response(response, "image post")

        except Exception as e:
            self.logger.error(f"Error posting image: {e}")
            return None

    def post_video(
        self,
        video_path: str,
        title: str = "",
        description: str = "",
        published: bool = True,
        scheduled_publish_time: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Post a video to the page.

        Args:
            video_path: Path to video file
            title: Video title
            description: Video description
            published: Whether to publish immediately
            scheduled_publish_time: Unix timestamp for scheduled publishing

        Returns:
            Post response data or None on failure
        """
        try:
            # Upload video directly to /videos endpoint
            video_id = self._upload_video(video_path, title, description)
            if not video_id:
                return None

            # For video posts, the video IS the post when uploaded to /videos
            # The video IS the post, no need to create a separate feed post
            # Just wait for processing to complete
            if published:
                processing_ok = self._wait_for_video_processing(video_id)
                if not processing_ok:
                    self.logger.warning(f"Video {video_id} processing check failed, but upload succeeded")

            # Try to get post info, but don't fail if it doesn't exist
            video_data = self.get_post(video_id)
            if video_data:
                return video_data

            # Video uploaded successfully but status check failed (soft error)
            # This can happen if the video ID format is different from post ID format
            self.logger.warning(f"Video uploaded successfully, but status check returned 400 - video ID: {video_id}")
            return {"id": video_id, "uploaded": True}

        except Exception as e:
            self.logger.error(f"Error posting video: {e}")
            return None

    def post_link(
        self,
        link: str,
        message: str = "",
        published: bool = True,
        scheduled_publish_time: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Post a link to the page.

        Args:
            link: URL to share
            message: Optional message
            published: Whether to publish immediately
            scheduled_publish_time: Unix timestamp for scheduled publishing

        Returns:
            Post response data or None on failure
        """
        try:
            url = f"{self.base_url}/{self.page_id}/feed"

            data = {
                "link": link,
                "message": message,
                "published": "true" if published else "false"
            }

            if scheduled_publish_time and not published:
                data["scheduled_publish_time"] = str(scheduled_publish_time)
                data["published"] = "false"

            response = self.session.post(url, data=data, timeout=self.timeout)

            return self._handle_response(response, "link post")

        except Exception as e:
            self.logger.error(f"Error posting link: {e}")
            return None

    def _upload_photo(self, image_path: str) -> Optional[str]:
        """Upload a photo to Facebook and return media ID."""
        try:
            path = Path(image_path)
            if not path.exists():
                self.logger.error(f"Image file not found: {image_path}")
                return None

            # Check file size
            file_size = path.stat().st_size
            if file_size > 50 * 1024 * 1024:  # 50MB limit
                self.logger.error(f"Image file too large: {file_size} bytes (max 50MB)")
                return None

            url = f"{self.base_url}/{self.page_id}/photos"

            with open(path, 'rb') as f:
                files = {'source': (path.name, f, 'image/' + path.suffix[1:])}
                data = {"published": "false"}

                response = self.session.post(url, files=files, data=data, timeout=self.timeout)

            result = self._handle_response(response, "photo upload")
            if result and "id" in result:
                self.logger.info(f"Photo uploaded successfully: {result['id']}")
                return result["id"]

            return None

        except Exception as e:
            self.logger.error(f"Error uploading photo: {e}")
            return None

    def _upload_video(
        self,
        video_path: str,
        title: str = "",
        description: str = ""
    ) -> Optional[str]:
        """Upload a video to Facebook using /videos endpoint."""
        try:
            path = Path(video_path)
            if not path.exists():
                self.logger.error(f"Video file not found: {video_path}")
                return None

            file_size = path.stat().st_size
            if file_size > 4 * 1024 * 1024 * 1024:  # 4GB limit
                self.logger.error(f"Video file too large: {file_size} bytes (max 4GB)")
                return None

            # Upload video to /videos endpoint (correct endpoint for Page videos)
            url = f"{self.base_url}/{self.page_id}/videos"

            # For large videos, use resumable upload
            if file_size > 100 * 1024 * 1024:  # > 100MB
                return self._upload_video_resumable(path, title, description)

            # Simple upload for smaller videos
            with open(path, 'rb') as f:
                files = {'source': (path.name, f, 'video/' + path.suffix[1:])}
                data = {
                    "title": title or path.name,
                    "description": description,
                    "published": "true"  # Publish immediately
                }

                response = self.session.post(url, files=files, data=data, timeout=self.timeout * 3)

            result = self._handle_response(response, "video upload")
            if result and "id" in result:
                self.logger.info(f"Video uploaded successfully: {result['id']}")
                return result["id"]

            return None

        except Exception as e:
            self.logger.error(f"Error uploading video: {e}")
            return None

    def _upload_video_resumable(
        self,
        path: Path,
        title: str,
        description: str
    ) -> Optional[str]:
        """Upload large video using resumable upload."""
        try:
            file_size = path.stat().st_size

            # Phase 1: Start upload session
            start_url = f"{self.base_url}/{self.page_id}/videos"
            start_data = {
                "upload_phase": "start",
                "file_size": str(file_size),
                "title": title or path.name,
                "description": description
            }

            response = self.session.post(start_url, data=start_data, timeout=self.timeout)
            result = self._handle_response(response, "video upload start")

            if not result or "video_id" not in result:
                return None

            video_id = result["video_id"]
            upload_session_id = result.get("upload_session_id", video_id)

            # Phase 2: Upload chunks
            chunk_size = 4 * 1024 * 1024  # 4MB chunks
            with open(path, 'rb') as f:
                offset = 0
                while offset < file_size:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break

                    transfer_url = f"{self.base_url}/{upload_session_id}"
                    transfer_data = {
                        "upload_phase": "transfer",
                        "start_offset": str(offset)
                    }

                    files = {'video_file_chunk': (f'chunk_{offset}', chunk, 'video/mp4')}
                    response = self.session.post(transfer_url, files=files, data=transfer_data, timeout=self.timeout)

                    result = self._handle_response(response, f"video chunk at offset {offset}")
                    if not result:
                        return None

                    offset += len(chunk)

            # Phase 3: Finish upload
            finish_url = f"{self.base_url}/{self.page_id}/videos"
            finish_data = {
                "upload_phase": "finish",
                "video_id": video_id
            }

            response = self.session.post(finish_url, data=finish_data, timeout=self.timeout)
            result = self._handle_response(response, "video upload finish")

            if result and "id" in result:
                self.logger.info(f"Resumable video upload completed: {result['id']}")
                return result["id"]

            return None

        except Exception as e:
            self.logger.error(f"Error in resumable video upload: {e}")
            return None

    def _wait_for_video_processing(self, video_id: str, max_wait: int = 300) -> bool:
        """Wait for video to finish processing."""
        self.logger.info(f"Waiting for video {video_id} to process...")
        start_time = time.time()

        while time.time() - start_time < max_wait:
            try:
                video = self.get_post(video_id)
                if video:
                    # Check if video is ready
                    status = video.get("status", {})
                    if status.get("video_status") == "ready":
                        self.logger.info(f"Video {video_id} processed successfully")
                        return True
                    elif status.get("video_status") in ["error", "expired"]:
                        self.logger.error(f"Video processing failed: {status.get('video_status')}")
                        return False
            except Exception as e:
                # Don't log error for 400 responses - video may have uploaded successfully
                # but the ID format differs from post ID format
                if "400" not in str(e):
                    self.logger.warning(f"Error checking video status: {e}")

            time.sleep(10)

        self.logger.warning(f"Video processing timeout after {max_wait}s")
        return False

    def _handle_response(self, response: requests.Response, operation: str) -> Optional[Dict[str, Any]]:
        """Handle API response and log errors."""
        try:
            data = response.json()
        except json.JSONDecodeError:
            self.logger.error(f"{operation} failed: Invalid JSON response - {response.text[:500]}")
            return None

        # ALWAYS log the full response for debugging
        self.logger.debug(f"{operation} response: {json.dumps(data, indent=2)}")

        if response.status_code == 200:
            self.logger.info(f"{operation} successful: {data.get('id', 'no ID')}")
            return data
        else:
            error = data.get("error", {})
            error_code = error.get("code", "unknown")
            error_msg = error.get("message", "Unknown error")
            error_subcode = error.get("error_subcode", "")

            self.logger.error(
                f"{operation} failed: [{error_code}] {error_msg}"
                + (f" (subcode: {error_subcode})" if error_subcode else "")
            )
            self.logger.debug(f"Full error response: {json.dumps(data, indent=2)}")

            # Log specific error handling
            if error_code == 190:
                self.logger.error("Access token may be expired or invalid")
            elif error_code == 100:
                self.logger.error("Invalid parameter or missing permission")
            elif error_code == 4:
                self.logger.error("Rate limit exceeded")
            elif error_code == 368:
                self.logger.error("Action blocked or spam detected")

            return None

    def get_post(self, post_id: str) -> Optional[Dict[str, Any]]:
        """Get post information."""
        try:
            url = f"{self.base_url}/{post_id}"
            # Only request fields that exist on ALL post types (videos, photos, links, text)
            params = {"fields": "id,created_time,permalink_url,status", "access_token": self.access_token}

            response = self.session.get(url, params=params, timeout=self.timeout)

            if response.status_code == 200:
                return response.json()
            else:
                self._log_error_response(response, "Get post")
                return None

        except Exception as e:
            self.logger.error(f"Error getting post: {e}")
            return None

    def delete_post(self, post_id: str) -> bool:
        """Delete a post."""
        try:
            url = f"{self.base_url}/{post_id}"
            response = self.session.delete(url, timeout=self.timeout)

            if response.status_code == 200:
                self.logger.info(f"Post deleted: {post_id}")
                return True
            else:
                self._log_error_response(response, "Delete post")
                return False

        except Exception as e:
            self.logger.error(f"Error deleting post: {e}")
            return False

    def get_post_insights(self, post_id: str, metrics: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Get post insights/metrics."""
        if metrics is None:
            metrics = ["post_impressions", "post_engaged_users", "post_clicks", "post_reactions_like_total"]

        try:
            url = f"{self.base_url}/{post_id}/insights"
            params = {"metric": ",".join(metrics), "access_token": self.access_token}

            response = self.session.get(url, params=params, timeout=self.timeout)

            if response.status_code == 200:
                return response.json()
            else:
                self._log_error_response(response, "Get post insights")
                return None

        except Exception as e:
            self.logger.error(f"Error getting post insights: {e}")
            return None

    def _log_error_response(self, response: requests.Response, operation: str):
        """Log error response details."""
        try:
            data = response.json()
            self.logger.error(f"{operation} failed: {response.status_code} - {json.dumps(data, indent=2)}")
        except:
            self.logger.error(f"{operation} failed: {response.status_code} - {response.text[:500]}")