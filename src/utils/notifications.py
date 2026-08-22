"""
Notifications Module
Handles desktop notifications for the application.
"""

import logging
import platform
import subprocess
import sys
from typing import Optional, Dict, Any


class NotificationManager:
    """
    Manages desktop notifications across platforms.

    Supports Windows, macOS, and Linux notifications.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize the Notification Manager.

        Args:
            config: Notification configuration
        """
        self.config = config
        self.enabled = config.get("enabled", True)
        self.title = config.get("title", "Facebook Auto Poster")
        self.logger = logging.getLogger(__name__)

    def send(
        self,
        message: str,
        title: Optional[str] = None,
        urgency: str = "normal"
    ) -> bool:
        """
        Send a desktop notification.

        Args:
            message: Notification message
            title: Notification title (optional, uses default if not provided)
            urgency: Notification urgency (low, normal, critical)

        Returns:
            True if notification was sent successfully
        """
        if not self.enabled:
            return False

        notification_title = title or self.title

        try:
            system = platform.system().lower()

            if system == "windows":
                return self._send_windows(notification_title, message, urgency)
            elif system == "darwin":
                return self._send_macos(notification_title, message)
            elif system == "linux":
                return self._send_linux(notification_title, message, urgency)
            else:
                self.logger.warning(f"Unsupported platform for notifications: {system}")
                return False

        except Exception as e:
            self.logger.error(f"Failed to send notification: {e}")
            return False

    def _send_windows(self, title: str, message: str, urgency: str) -> bool:
        """Send notification on Windows."""
        try:
            # Try using win10toast if available
            try:
                from win10toast import ToastNotifier
                toaster = ToastNotifier()
                toaster.show_toast(
                    title,
                    message,
                    duration=10,
                    threaded=True
                )
                return True
            except ImportError:
                pass

            # Fallback: Use PowerShell with BurntToast module
            try:
                ps_script = f'''
                if (Get-Module -ListAvailable -Name BurntToast) {{
                    Import-Module BurntToast
                    New-BurntToastNotification -Text "{title}", "{message}"
                }} else {{
                    # Fallback to simple balloon tip
                    Add-Type -AssemblyName System.Windows.Forms
                    $notify = New-Object System.Windows.Forms.NotifyIcon
                    $notify.Icon = [System.Drawing.SystemIcons]::Information
                    $notify.Visible = $true
                    $notify.ShowBalloonTip(10000, "{title}", "{message}", "Info")
                }}
                '''
                subprocess.run(
                    ["powershell", "-Command", ps_script],
                    capture_output=True,
                    timeout=5
                )
                return True
            except Exception:
                pass

            # Final fallback: Print to console
            print(f"🔔 [{title}] {message}")
            return True

        except Exception as e:
            self.logger.debug(f"Windows notification failed: {e}")
            return False

    def _send_macos(self, title: str, message: str) -> bool:
        """Send notification on macOS."""
        try:
            # Use osascript for native notifications
            script = f'''
            display notification "{message}" with title "{title}"
            '''
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5
            )
            return True
        except Exception as e:
            self.logger.debug(f"macOS notification failed: {e}")
            return False

    def _send_linux(self, title: str, message: str, urgency: str) -> bool:
        """Send notification on Linux."""
        try:
            # Try notify-send (libnotify)
            urgency_map = {
                "low": "low",
                "normal": "normal",
                "critical": "critical"
            }
            notify_urgency = urgency_map.get(urgency, "normal")

            subprocess.run(
                ["notify-send", "-u", notify_urgency, title, message],
                capture_output=True,
                timeout=5
            )
            return True
        except FileNotFoundError:
            try:
                # Try zenity as fallback
                subprocess.run(
                    ["zenity", "--notification", "--text", f"{title}: {message}"],
                    capture_output=True,
                    timeout=5
                )
                return True
            except FileNotFoundError:
                pass
            return False
        except Exception as e:
            self.logger.debug(f"Linux notification failed: {e}")
            return False

    def send_startup(self):
        """Send startup notification."""
        self.send(
            "Facebook Auto Poster started successfully",
            "Application Started"
        )

    def send_shutdown(self):
        """Send shutdown notification."""
        self.send(
            "Facebook Auto Poster stopped",
            "Application Stopped"
        )

    def send_post_success(self, content_title: str):
        """Send successful post notification."""
        self.send(
            f"Successfully posted: {content_title}",
            "Post Published ✓"
        )

    def send_post_failure(self, content_title: str, error: str):
        """Send post failure notification."""
        self.send(
            f"Failed to post: {content_title}\nError: {error}",
            "Post Failed ✗",
            urgency="critical"
        )


def create_notification_manager(config: Optional[Dict[str, Any]] = None) -> NotificationManager:
    """Factory function to create NotificationManager."""
    if config is None:
        config = {"enabled": True, "title": "Facebook Auto Poster"}
    return NotificationManager(config)