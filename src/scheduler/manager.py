"""
Scheduler Manager
Handles scheduling and execution of posting jobs using APScheduler.

FIXED: Proper timezone handling, job tracking, and terminal visibility for scheduled posts.
"""

import logging
import pytz
from datetime import datetime, time as dt_time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor

from src.facebook.poster import FacebookPoster
from src.content.manager import ContentManager, ContentType
from src.ui.console import console, ICONS
from src.ui.messages import Messages


@dataclass
class ScheduledJob:
    """Represents a scheduled posting job."""
    id: str
    content_id: str
    scheduled_time: dt_time
    days: List[str] = field(default_factory=lambda: ["mon", "tue", "wed", "thu", "fri", "sat", "sun"])
    enabled: bool = True
    last_run: Optional[datetime] = None
    next_run: Optional[datetime] = None


class SchedulerManager:
    """
    Manages scheduled posting jobs using APScheduler.

    Supports daily, weekly, and custom schedules with timezone awareness.
    FIXED: Proper job tracking, terminal visibility, and error handling.
    """

    def __init__(
        self,
        poster: FacebookPoster,
        content_manager: ContentManager,
        logger: logging.Logger,
        config: Dict[str, Any]
    ):
        """
        Initialize the Scheduler Manager.

        Args:
            poster: FacebookPoster instance
            content_manager: ContentManager instance
            logger: Logger instance
            config: Scheduler configuration dictionary
        """
        self.poster = poster
        self.content_manager = content_manager
        self.logger = logger
        self.config = config

        # Job storage
        self.jobs: Dict[str, ScheduledJob] = {}

        # Configure scheduler with proper timezone
        timezone_str = config.get("timezone", "Asia/Karachi")
        try:
            self.timezone = pytz.timezone(timezone_str)
        except Exception:
            self.logger.warning(f"Invalid timezone '{timezone_str}', falling back to Asia/Karachi")
            self.timezone = pytz.timezone("Asia/Karachi")

        misfire_grace_time = config.get("misfire_grace_time", 300)
        coalesce = config.get("coalesce", True)
        max_instances = config.get("max_instances", 1)

        jobstores = {"default": MemoryJobStore()}
        executors = {"default": ThreadPoolExecutor(max_workers=3)}
        job_defaults = {
            "coalesce": coalesce,
            "max_instances": max_instances,
            "misfire_grace_time": misfire_grace_time
        }

        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=self.timezone
        )

        self.logger.info(f"Scheduler initialized with timezone: {self.timezone}")

    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            self.logger.info("Scheduler started")
            console.print(f"[cyan]{ICONS['cog']} Scheduler started[/cyan]")

            # Log next run times for all jobs
            for job in self.scheduler.get_jobs():
                next_run = getattr(job, 'next_run_time', None)
                self.logger.info(f"Next run for {job.id}: {next_run} ({self.timezone})")

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            self.logger.info("Scheduler stopped")
            console.print(f"[cyan]{ICONS['cog']} Scheduler stopped[/cyan]")

    def add_job(self, job: ScheduledJob) -> bool:
        """
        Add a scheduled job.

        Args:
            job: ScheduledJob to add

        Returns:
            True if added successfully
        """
        try:
            if not job.enabled:
                self.logger.info(f"Job {job.id} is disabled, skipping")
                return True

            # Skip content check for jobs with empty content_id (dynamic assignment)
            # These are daily jobs that get content assigned later
            if job.content_id and job.content_id not in self.content_manager.content_items:
                self.logger.error(f"Content not found for job {job.id}: {job.content_id}")
                return False

            # Build cron expression from days
            day_map = {
                "mon": "mon", "tue": "tue", "wed": "wed",
                "thu": "thu", "fri": "fri", "sat": "sat", "sun": "sun"
            }
            cron_days = ",".join(day_map.get(d.lower()[:3], d) for d in job.days)

            # Create CronTrigger with proper timezone
            trigger = CronTrigger(
                day_of_week=cron_days,
                hour=job.scheduled_time.hour,
                minute=job.scheduled_time.minute,
                timezone=self.timezone
            )

            # IMPORTANT: Register job in self.jobs FIRST, then add to APScheduler
            # This ensures the job exists in our tracking when APScheduler executes it
            self.jobs[job.id] = job

            # Add job to scheduler
            aps_job = self.scheduler.add_job(
                self._execute_job,
                trigger=trigger,
                args=[job.id],
                id=job.id,
                name=f"Post: {job.content_id or 'dynamic'}",
                replace_existing=True
            )

            # Update job info - safely access next_run_time
            next_run = getattr(aps_job, 'next_run_time', None)
            job.next_run = next_run

            self.logger.info(f"Added scheduled job: {job.id} at {job.scheduled_time} ({self.timezone}) on {cron_days}")
            console.print(f"[cyan]{ICONS['cog']}[/cyan] Added job: {job.id} at {job.scheduled_time.strftime('%H:%M')} PKT daily")
            return True

        except Exception as e:
            self.logger.error(f"Failed to add job {job.id}: {e}")
            console.print(f"[error]{ICONS['x']} ERROR adding job {job.id}: {e}[/error]")
            # Clean up if failed
            if job.id in self.jobs:
                del self.jobs[job.id]
            return False

    def remove_job(self, job_id: str) -> bool:
        """
        Remove a scheduled job.

        Args:
            job_id: ID of job to remove

        Returns:
            True if removed successfully
        """
        try:
            self.scheduler.remove_job(job_id)
            if job_id in self.jobs:
                del self.jobs[job_id]
            self.logger.info(f"Removed job: {job_id}")
            console.print(f"[cyan]{ICONS['cog']}[/cyan] Removed job: {job_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to remove job {job_id}: {e}")
            return False

    def enable_job(self, job_id: str) -> bool:
        """Enable a scheduled job."""
        if job_id in self.jobs:
            job = self.jobs[job_id]
            job.enabled = True
            return self.add_job(job)
        return False

    def disable_job(self, job_id: str) -> bool:
        """Disable a scheduled job."""
        if job_id in self.jobs:
            job = self.jobs[job_id]
            job.enabled = False
            return self.remove_job(job_id)
        return False

    def list_jobs(self) -> List[ScheduledJob]:
        """Get list of all scheduled jobs."""
        # Update next_run times from scheduler
        for aps_job in self.scheduler.get_jobs():
            if aps_job.id in self.jobs:
                next_run = getattr(aps_job, 'next_run_time', None)
                self.jobs[aps_job.id].next_run = next_run

        return list(self.jobs.values())

    def get_job(self, job_id: str) -> Optional[ScheduledJob]:
        """Get a specific job by ID."""
        return self.jobs.get(job_id)

    def _execute_job(self, job_id: str):
        """
        Execute a scheduled posting job.

        Args:
            job_id: ID of job to execute
        """
        # Print clear terminal message for scheduled execution using Messages
        from src.ui.messages import Messages
        Messages.print_scheduled_post_header(job_id, "")

        # Check if job exists in our tracking
        if job_id not in self.jobs:
            self.logger.warning(f"Job not found in tracking: {job_id}")
            console.print(f"[warning]{ICONS['warning']} WARNING: Job {job_id} not found in tracking![/warning]")
            return

        job = self.jobs[job_id]

        if not job.enabled:
            self.logger.info(f"Job {job_id} is disabled, skipping")
            console.print(f"[cyan]{ICONS['cog']}[/cyan] Job {job_id} is disabled, skipping")
            return

        # Check if content_id is empty (dynamic job)
        if not job.content_id:
            self.logger.info(f"Job {job_id} has no content assigned, skipping")
            console.print(f"[cyan]{ICONS['cog']}[/cyan] Job {job_id} has no content assigned, skipping")
            return

        # Get content info for display
        content = self.content_manager.get_content(job.content_id)
        content_title = content.title if content else "Unknown"

        self.logger.info(f"Executing scheduled job: {job_id} (content: {job.content_id})")
        console.print(f"[cyan]{ICONS['rocket']} Starting post for: {content_title}[/cyan]")
        console.print(f"[cyan]{ICONS['link']} Content ID: {job.content_id}[/cyan]")
        console.print(f"[cyan]{ICONS['clock']} Scheduled time: {job.scheduled_time.strftime('%H:%M')} PKT[/cyan]")

        try:
            # Call the same post_content method used by direct posting
            Messages.print_posting_started()
            success = self.poster.post_content(job.content_id)

            job.last_run = datetime.now(self.timezone)

            # Update next run time from scheduler
            aps_job = self.scheduler.get_job(job_id)
            if aps_job:
                next_run = getattr(aps_job, 'next_run_time', None)
                job.next_run = next_run

            if success:
                self.logger.info(f"Job {job_id} completed successfully")
                console.print(f"[success]{ICONS['check']} SUCCESS: {content_title} posted to Facebook![/success]")
            else:
                self.logger.error(f"Job {job_id} failed to post content")
                console.print(f"[error]{ICONS['x']} FAILED: {content_title} - Check logs for details[/error]")

        except Exception as e:
            self.logger.error(f"Job {job_id} execution error: {e}", exc_info=True)
            console.print(f"[error]{ICONS['x']} ERROR: {job_id} - {e}[/error]")

    def add_one_time_job(
        self,
        job_id: str,
        content_id: str,
        run_time: datetime
    ) -> bool:
        """
        Add a one-time scheduled job.

        Args:
            job_id: Unique job ID
            content_id: Content to post
            run_time: When to run (datetime)

        Returns:
            True if added successfully
        """
        try:
            if content_id not in self.content_manager.content_items:
                self.logger.error(f"Content not found: {content_id}")
                return False

            # Ensure run_time is timezone-aware
            if run_time.tzinfo is None:
                run_time = self.timezone.localize(run_time)

            trigger = DateTrigger(run_date=run_time, timezone=self.timezone)

            # Register job first
            job = ScheduledJob(
                id=job_id,
                content_id=content_id,
                scheduled_time=run_time.time(),
                days=["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
                enabled=True
            )
            self.jobs[job_id] = job

            aps_job = self.scheduler.add_job(
                self._execute_job,
                trigger=DateTrigger(run_date=run_time, timezone=self.timezone),
                args=[job_id],
                id=job_id,
                name=f"One-time: {content_id}",
                replace_existing=True
            )

            job.next_run = getattr(aps_job, 'next_run_time', None)

            self.logger.info(f"Added one-time job: {job_id} at {run_time}")
            console.print(f"[cyan]{ICONS['cog']}[/cyan] Added one-time job: {job_id} at {run_time}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to add one-time job: {e}")
            console.print(f"[error]{ICONS['x']} ERROR adding one-time job: {e}[/error]")
            return False

    def reschedule_job(self, job_id: str, new_time: dt_time, new_days: Optional[List[str]] = None) -> bool:
        """Reschedule an existing job."""
        if job_id not in self.jobs:
            self.logger.error(f"Job not found: {job_id}")
            return False

        job = self.jobs[job_id]
        job.scheduled_time = new_time
        if new_days:
            job.days = new_days

        # Remove old and add new
        self.remove_job(job_id)
        return self.add_job(job)

    def get_status(self) -> Dict[str, Any]:
        """Get scheduler status."""
        return {
            "running": self.scheduler.running,
            "timezone": str(self.timezone),
            "jobs_count": len(self.jobs),
            "jobs": [
                {
                    "id": job.id,
                    "content_id": job.content_id,
                    "time": job.scheduled_time.strftime("%H:%M"),
                    "days": job.days,
                    "enabled": job.enabled,
                    "last_run": job.last_run.isoformat() if job.last_run else None,
                    "next_run": job.next_run.isoformat() if job.next_run else None
                }
                for job in self.jobs.values()
            ]
        }