"""
Rich Messages Module
Provides styled terminal messages for various events.
"""

from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich.text import Text
from rich.align import Align
from typing import Optional, Any, Dict, List
from datetime import datetime
from pathlib import Path

from src.ui.console import console, COLORS, ICONS


class Messages:
    """Provides styled terminal output for various messages."""

    @staticmethod
    def print_banner(title: str = "Facebook Auto Poster", version: str = "2.0.0"):
        """Print the application banner."""
        console.print()
        console.print(Align.center(Text.assemble(
            (f"  ╔══════════════════════════════════════════════════════════╗  ", "header"),
            ("  ║  ", "header"),
            (f"  📱 FACEBOOK PAGE AUTO POSTER", "header"),
            ("  ║  ", "header"),
            ("  ", "header"),
            (f"  Version {version}", "dim"),
            ("  ║  ", "header"),
            ("  ╚══════════════════════════════════════════════════════════╝  ", "header"),
        ), vertical="middle"))
        console.print()

    @staticmethod
    def print_rule(title: str = ""):
        """Print a styled rule separator."""
        console.print(Rule(title, style="rule"))

    @staticmethod
    def print_success(message: str):
        """Print a success message with green checkmark."""
        console.print(f"[success]{ICONS['check']} {message}[/success]")

    @staticmethod
    def print_error(message: str):
        """Print an error message with red X."""
        console.print(f"[error]{ICONS['x']} {message}[/error]")

    @staticmethod
    def print_warning(message: str):
        """Print a warning message with yellow warning icon."""
        console.print(f"[warning]{ICONS['warning']} {message}[/warning]")

    @staticmethod
    def print_info(message: str):
        """Print an info message."""
        console.print(f"[info]{ICONS['info']} {message}[/info]")

    @staticmethod
    def print_scheduled(message: str):
        """Print a scheduled job message."""
        console.print(f"[job]{ICONS['rocket']} {message}[/job]")

    @staticmethod
    def print_downloading(message: str):
        """Print a downloading message."""
        console.print(f"[cyan]{ICONS['package']} {message}[/cyan]")

    @staticmethod
    def print_connection_test(success: bool, page_name: str = "", page_id: str = ""):
        """Print connection test result."""
        if success:
            console.print()
            console.print(Panel(
                Text.assemble(
                    (f"{ICONS['check']} Facebook API Connection Successful!\n", "success"),
                    (f"  Page: ", "dim"),
                    (f"{page_name}", "green"),
                    (f"\n  Page ID: ", "dim"),
                    (f"{page_id}", "cyan"),
                ),
                title="Connection Test",
                border_style="green",
                expand=False
            ))
            console.print()
        else:
            console.print()
            console.print(Panel(
                Text.assemble(
                    (f"{ICONS['x']} Facebook API Connection Failed!\n", "error"),
                    ("  Please check your credentials in .env file", "dim"),
                ),
                title="Connection Test",
                border_style="red",
                expand=False
            ))
            console.print()

    @staticmethod
    def print_schedule_summary(jobs: List[Dict[str, Any]]):
        """Print a summary of scheduled jobs in a table."""
        if not jobs:
            console.print("[info]No scheduled jobs configured.[/info]")
            return

        table = Table(title=f"{ICONS['calendar']} Scheduled Jobs (Pakistan Timezone - Asia/Karachi)", show_header=True, header_style="cyan")
        table.add_column("Job ID", style="cyan", width=12)
        table.add_column("Time (PKT)", style="green", width=12)
        table.add_column("Video URL", style="blue", min_width=40)
        table.add_column("Status", style="yellow", width=10)

        for job in jobs:
            status = "[green]Enabled[/green]" if job.get("enabled", True) else "[red]Disabled[/red]"
            url_short = job.get("video_url", "")[:40] + "..." if len(job.get("video_url", "")) > 40 else job.get("video_url", "")
            table.add_row(
                job.get("id", "unknown"),
                job.get("time", "N/A"),
                url_short,
                status
            )

        console.print()
        console.print(table)
        console.print()

    @staticmethod
    def print_job_queued(job_id: str, scheduled_time: str):
        """Print message when a job is queued."""
        console.print(f"[green]{ICONS['check']} Scheduled job '{job_id}' at {scheduled_time} PKT[/green]")

    @staticmethod
    def print_schedule_configured(schedule_info: List[Dict[str, Any]]):
        """Print the schedule configuration summary."""
        console.print()
        console.print(Rule("="))

        # Create summary table
        table = Table(show_header=False, box=None)
        table.add_column("style", width=10)
        table.add_column("content", width=30)

        for i, info in enumerate(schedule_info, 1):
            table.add_row("", f"[green]{ICONS['check']}[/green] Post {i}: {info['time']} PKT")

        console.print(table)
        console.print(Rule("="))
        console.print()

    @staticmethod
    def print_download_progress(url: str, title: str = ""):
        """Print download progress message."""
        url_display = url[:50] + "..." if len(url) > 50 else url
        console.print(f"\n[cyan]{ICONS['video']} Downloading video from:[/cyan] [url]{url_display}[/url]")
        if title:
            console.print(f"[dim]Title: {title}[/dim]")

    @staticmethod
    def print_download_progress_bar(downloader, url: str):
        """Print a progress bar for video download using rich progress."""
        from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, DownloadColumn

        url_display = url[:40] + "..." if len(url) > 40 else url

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            DownloadColumn(),
            TextColumn("[progress.elapsed][Time left: {task.remaining}]"),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task(f"[cyan]{ICONS['package']} Downloading: {url_display}[/cyan]", total=100)

            # Simulate progress - in real implementation, this would be updated by the downloader
            # For now, we just show a spinner-like animation
            import time
            for i in range(100):
                progress.update(task, completed=i + 1)
                time.sleep(0.02)  # Simulate download time
                if progress.finished:
                    break

    @staticmethod
    def print_download_complete(title: str, file_path: Optional[Path] = None):
        """Print download completion message."""
        safe_title = title.encode('ascii', 'ignore').decode('ascii') if title else "Video"
        console.print(f"[green]{ICONS['check']} Downloaded: {safe_title}[/green]")
        if file_path:
            console.print(f"[dim]  Saved to: {file_path}[/dim]")

    @staticmethod
    def print_download_failed(error_message: str):
        """Print download failure message."""
        console.print(f"[error]{ICONS['x']} Download failed: {error_message}[/error]")

    @staticmethod
    def print_wrong_video_error(error_message: str):
        """Print wrong video error message - downloaded file doesn't match queued video."""
        console.print(f"[error]{ICONS['x']} {error_message}[/error]")

    @staticmethod
    def print_content_added(content_id: str, title: str):
        """Print message when content is added to manager."""
        safe_title = title.encode('ascii', 'ignore').decode('ascii') if title else "Video"
        console.print(f"[cyan]{ICONS['video']} Added video: {content_id}[/cyan]")

    @staticmethod
    def print_posting_started():
        """Print message when posting starts."""
        console.print(f"\n[cyan]{ICONS['rocket']} Calling Facebook API to post...[/cyan]")

    @staticmethod
    def print_post_success(title: str):
        """Print successful post message."""
        safe_title = title.encode('ascii', 'ignore').decode('ascii') if title else "Video"
        console.print()
        console.print(Panel(
            Text.assemble(
                (f"{ICONS['check']} {safe_title} posted to Facebook!\n", "success"),
                (f"{ICONS['rocket']} Video uploaded successfully", "green"),
            ),
            border_style="green",
            expand=False
        ))

    @staticmethod
    def print_post_failure(message: str):
        """Print post failure message."""
        console.print()
        console.print(Panel(
            Text.assemble(
                (f"{ICONS['x']} Failed to post\n", "error"),
                ("[dim]Check logs for details[/dim]", "dim"),
            ),
            border_style="red",
            expand=False
        ))

    @staticmethod
    def print_post_error(job_id: str, error: str):
        """Print post error message."""
        console.print(f"[error]{ICONS['x']} {job_id} - {error}[/error]")

    @staticmethod
    def print_scheduled_post_header(job_id: str, scheduled_time: str):
        """Print header for scheduled post execution."""
        console.print()
        console.print(Rule("="))
        console.print(Text.assemble(
            (f"{ICONS['rocket']} SCHEDULED POST: Executing job: ", "cyan"),
            (f"{job_id}", "green"),
        ))
        console.print(Rule("="))
        console.print()

    @staticmethod
    def print_job_info(video_url: str, scheduled_time: str):
        """Print job information during execution."""
        url_display = video_url[:60] + "..." if len(video_url) > 60 else video_url
        console.print(f"[cyan]{ICONS['link']} Video URL:[/cyan] {url_display}")
        console.print(f"[cyan]{ICONS['clock']} Scheduled time:[/cyan] {scheduled_time} PKT")

    @staticmethod
    def print_completion_message():
        """Print the final completion message."""
        console.print()
        console.print(Panel(
            Text.assemble(
                (f"{ICONS['check']} All posts completed successfully!\n", "success"),
                (f"{ICONS['sparkles']} Facebook Auto Poster finished.\n", "green"),
            ),
            border_style="green",
            expand=False
        ))
        console.print()

    @staticmethod
    def print_status(state: str, running: bool, jobs_count: int, content_count: int, facebook_connected: bool):
        """Print application status."""
        status_color = "green" if running else "red"
        fb_status = "green" if facebook_connected else "red"
        fb_icon = ICONS['check'] if facebook_connected else ICONS['x']

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("label", style="cyan", width=15)
        table.add_column("value", width=30)

        table.add_row("State", f"[{status_color}]{state}[/{status_color}]")
        table.add_row("Running", f"[{status_color}]{running}[/{status_color}]")
        table.add_row("Jobs Scheduled", str(jobs_count))
        table.add_row("Content Items", str(content_count))
        table.add_row("Facebook Connected", f"[{fb_status}]{fb_icon} {str(facebook_connected)}[/{fb_status}]")

        console.print()
        console.print(Panel(table, title="Application Status", border_style="cyan"))
        console.print()

    @staticmethod
    def print_download_failed_content(error_message: str):
        """Print message when content download fails."""
        console.print(f"[error]{ICONS['x']} FAILED: Could not download video - {error_message}[/error]")

    @staticmethod
    def print_no_content_message():
        """Print message when content cannot be added to manager."""
        console.print(f"[error]{ICONS['x']} FAILED: Could not add content to manager[/error]")

    @staticmethod
    def print_initialization_message(message: str):
        """Print initialization message."""
        console.print(f"[cyan]{ICONS['cog']} {message}[/cyan]")

    @staticmethod
    def print_startup_message(num_posts: int):
        """Print startup message."""
        console.print()
        console.print(Panel(
            Text.assemble(
                (f"{ICONS['rocket']} Facebook Auto Poster Started\n", "green"),
                ("[dim]The application is running and will post", "dim"),
                (f"\n  {num_posts} posts scheduled daily.", "cyan"),
            ),
            border_style="green",
            expand=False
        ))
        console.print()

    @staticmethod
    def print_shutdown_message():
        """Print shutdown message."""
        console.print("[cyan][INFO] Stopping Facebook Auto Poster + Downloader...[/cyan]")

    @staticmethod
    def print_scheduler_started():
        """Print scheduler started message."""
        console.print(f"[cyan]{ICONS['cog']} Scheduler started[/cyan]")

    @staticmethod
    def print_scheduler_stopped():
        """Print scheduler stopped message."""
        console.print(f"[cyan]{ICONS['cog']} Scheduler stopped[/cyan]")

    @staticmethod
    def print_all_jobs_completed():
        """Print message when all jobs are completed."""
        console.print()
        console.print(Panel(
            Text.assemble(
                (f"{ICONS['check']} All posts completed successfully!\n", "success"),
                (f"{ICONS['sparkles']} Facebook Auto Poster finished.", "green"),
            ),
            border_style="green",
            expand=False
        ))
        console.print()