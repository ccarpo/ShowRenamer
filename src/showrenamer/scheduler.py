"""Central scheduler for file processing, retries and periodic re-scans."""
from pathlib import Path
from typing import Set, Dict, List, Callable, Optional, Tuple
from datetime import datetime, timedelta
import time
import threading
import logging

from showrenamer.renamer import NO_TARGET_DIR_REASON

logger = logging.getLogger(__name__)


class Scheduler:
    """Decides when video files are processed, retried, or re-scanned.

    The scheduler owns the lifecycle of a single worker thread. File-system
    events from watchdog and configuration-change events from ConfigWatcher
    are translated into scheduled tasks. A condition variable is used instead
    of polling so newly queued work is picked up immediately.
    """

    def __init__(self,
                 file_handler: Callable[[str], object],
                 watch_paths: List[str],
                 video_extensions: Set[str],
                 stability_period: int = 300,
                 retry_interval: int = 86400,
                 full_rescan_interval: int = 1800,
                 no_target_dir_retry_interval: int = 60,
                 max_retries: int = 3):
        self.file_handler = file_handler
        self.watch_paths = [Path(p).resolve() for p in watch_paths]
        self.video_extensions = video_extensions
        self.stability_period = stability_period
        self.retry_interval = retry_interval
        self.full_rescan_interval = full_rescan_interval
        self.no_target_dir_retry_interval = no_target_dir_retry_interval
        self.max_retries = max_retries

        # Files discovered by watchdog, waiting for stability_period after the
        # most recent event before they are processed.
        self.pending_processing: Dict[str, datetime] = {}

        # Files that failed processing and are waiting for retry.
        #   next_retry_at: when to try again
        #   retry_count:   hard-failure retry attempts consumed
        self.pending_retries: Dict[str, Tuple[datetime, int]] = {}

        # Paths currently being processed by the worker thread, used to avoid
        # processing the same file twice in parallel.
        self.in_progress: Set[str] = set()

        # Paths that have been successfully processed. They are skipped during
        # periodic full re-scans to avoid endless re-processing of unchanged
        # files. New file-system events remove a path from this set.
        self.processed_files: Set[str] = set()

        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.stop_event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None
        self.last_full_rescan: Optional[datetime] = None

    def start(self):
        """Start the scheduler worker thread."""
        self.stop_event.clear()
        self.worker_thread = threading.Thread(target=self._run, daemon=True)
        self.worker_thread.start()
        logger.info("Scheduler started")

    def stop(self):
        """Stop the scheduler and wait for the worker thread."""
        self.stop_event.set()
        with self.condition:
            self.condition.notify_all()
        if self.worker_thread:
            self.worker_thread.join(timeout=10)
        logger.info("Scheduler stopped")

    def add_file(self, file_path: Path):
        """Queue a file for processing once it has been stable."""
        if file_path.suffix.lower() not in self.video_extensions:
            return
        path_str = str(file_path)
        with self.condition:
            if path_str in self.in_progress:
                return
            # A new event on a previously processed file means it changed and
            # should be evaluated again.
            self.processed_files.discard(path_str)
            self.pending_processing[path_str] = datetime.now()
            self.condition.notify()

    def remove_file(self, file_path: Path):
        """Remove a file from all queues (e.g. deletion or move-out event)."""
        path_str = str(file_path)
        with self.condition:
            self.pending_processing.pop(path_str, None)
            self.pending_retries.pop(path_str, None)
            self.in_progress.discard(path_str)
            self.processed_files.discard(path_str)
            self.condition.notify()

    def schedule_full_rescan(self):
        """Schedule an immediate full re-scan of all watch paths."""
        with self.condition:
            self.last_full_rescan = None
            self.condition.notify()

    def schedule_config_rescan(self):
        """Reset retry state and re-scan all watch paths immediately.

        This is intended to be called whenever configuration (patterns,
        mapping or directories) changes, so that files which previously
        failed because of stale config are retried without waiting for the
        normal retry interval. Already successful files are also reconsidered
        once, in case the new config changes how they should be handled.
        """
        with self.condition:
            now = datetime.now()
            for path_str in list(self.pending_retries.keys()):
                self.pending_retries[path_str] = (now, 0)
            self.processed_files.clear()
            self.last_full_rescan = None
            self.condition.notify()

    def update_watch_paths(self, watch_paths: List[str]):
        """Replace the set of directories the scheduler watches."""
        with self.condition:
            self.watch_paths = [Path(p).resolve() for p in watch_paths]
            self.condition.notify()

    def _run(self):
        """Main scheduler loop."""
        while not self.stop_event.is_set():
            timeout = self._seconds_until_next_task()

            with self.condition:
                if not self.stop_event.is_set():
                    self.condition.wait(timeout=timeout)

            if self.stop_event.is_set():
                break

            self._run_due_tasks()

    def _seconds_until_next_task(self) -> float:
        """Return the number of seconds until the next due task, capped at 60s."""
        with self.condition:
            now = datetime.now()
            due_times = []

            for last_event_at in self.pending_processing.values():
                due_times.append(last_event_at + timedelta(seconds=self.stability_period))

            for next_retry_at, _ in self.pending_retries.values():
                due_times.append(next_retry_at)

            if self.last_full_rescan is None:
                due_times.append(now)
            else:
                due_times.append(self.last_full_rescan + timedelta(seconds=self.full_rescan_interval))

        if not due_times:
            return 60.0

        earliest = min(due_times)
        delta = (earliest - now).total_seconds()
        return max(0.0, min(delta, 60.0))

    def _run_due_tasks(self):
        """Execute all tasks that are due now."""
        now = datetime.now()

        # Full re-scan first so newly discovered files participate in the same
        # processing cycle.
        if self.last_full_rescan is None or (now - self.last_full_rescan).total_seconds() >= self.full_rescan_interval:
            self._full_rescan()
            self.last_full_rescan = now

        with self.condition:
            # Collect files whose stability period has elapsed.
            stable_files = [
                path_str for path_str, last_event_at in list(self.pending_processing.items())
                if (now - last_event_at).total_seconds() >= self.stability_period
            ]

            # Collect retries that are due.
            retry_files = [
                path_str for path_str, (next_retry_at, _) in list(self.pending_retries.items())
                if now >= next_retry_at
            ]

            for path_str in stable_files:
                self.pending_processing.pop(path_str, None)
                self.in_progress.add(path_str)

            for path_str in retry_files:
                self.pending_retries.pop(path_str, None)
                self.in_progress.add(path_str)

        # Process stable files outside the lock.
        for path_str in stable_files:
            if Path(path_str).exists():
                self._process_file(path_str)
            else:
                with self.condition:
                    self.in_progress.discard(path_str)

        # Retry pending files outside the lock.
        for path_str in retry_files:
            if Path(path_str).exists():
                self._retry_file(path_str)
            else:
                with self.condition:
                    self.in_progress.discard(path_str)

    def _full_rescan(self):
        """Walk watch paths and queue any video files not already handled."""
        for watch_path in self.watch_paths:
            if not watch_path.exists() or not watch_path.is_dir():
                continue
            logger.info(f"Full re-scan of {watch_path}")
            for file_path in watch_path.glob('**/*'):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in self.video_extensions:
                    continue
                path_str = str(file_path)
                with self.condition:
                    if path_str in self.in_progress:
                        continue
                    if path_str in self.pending_processing or path_str in self.pending_retries:
                        continue
                    if path_str in self.processed_files:
                        continue
                    self.pending_processing[path_str] = datetime.now()

    def _process_file(self, path_str: str):
        """Process a single file and re-queue on failure."""
        try:
            file_path = Path(path_str)
            if not self._is_file_stable(file_path):
                # File is still changing; re-queue with the current timestamp so
                # the stability window restarts.
                with self.condition:
                    self.pending_processing[path_str] = datetime.now()
                    self.in_progress.discard(path_str)
                return

            logger.info(f"Processing file: {file_path}")
            result = self.file_handler(path_str)
            success, reason = self._unpack_result(result)

            with self.condition:
                self.in_progress.discard(path_str)
                if success:
                    self.pending_retries.pop(path_str, None)
                    self.processed_files.add(path_str)
                    return

                if not file_path.exists():
                    return

                self._queue_retry(path_str, reason)

        except Exception as e:
            logger.error(f"Error processing {path_str}: {e}")
            with self.condition:
                self.in_progress.discard(path_str)
                if Path(path_str).exists():
                    self._queue_retry(path_str, str(e))

    def _retry_file(self, path_str: str):
        """Retry a pending file."""
        try:
            file_path = Path(path_str)
            if not file_path.exists():
                with self.condition:
                    self.in_progress.discard(path_str)
                return

            logger.info(f"Retrying file: {file_path}")
            result = self.file_handler(path_str)
            success, reason = self._unpack_result(result)

            with self.condition:
                self.in_progress.discard(path_str)
                if success:
                    self.pending_retries.pop(path_str, None)
                    self.processed_files.add(path_str)
                    return

                if not file_path.exists():
                    return

                self._queue_retry(path_str, reason)

        except Exception as e:
            logger.error(f"Error retrying {path_str}: {e}")
            with self.condition:
                self.in_progress.discard(path_str)
                if Path(path_str).exists():
                    self._queue_retry(path_str, str(e))

    def _queue_retry(self, path_str: str, reason: Optional[str]):
        """Queue a failed file for retry with appropriate backoff."""
        with self.condition:
            existing = self.pending_retries.get(path_str)
            retry_count = existing[1] if existing else 0

            if reason == NO_TARGET_DIR_REASON:
                # Transient failure: retry soon without consuming the hard-failure budget.
                next_retry_at = datetime.now() + timedelta(seconds=self.no_target_dir_retry_interval)
                self.pending_retries[path_str] = (next_retry_at, retry_count)
                logger.info(f"Queued for retry (target not ready): {path_str}")
                return

            if retry_count >= self.max_retries:
                logger.warning(f"Max retries reached for {path_str}. Giving up.")
                return

            # Exponential backoff with jitter, capped at retry_interval.
            delay = min(
                self.retry_interval,
                self.retry_interval * (0.5 ** (self.max_retries - retry_count - 1))
            )
            # Add small jitter to avoid thundering herd.
            delay = max(1, delay * (0.9 + 0.2 * (hash(path_str) % 1000) / 1000))
            next_retry_at = datetime.now() + timedelta(seconds=delay)
            self.pending_retries[path_str] = (next_retry_at, retry_count + 1)
            logger.info(f"Queued for retry ({retry_count + 1}/{self.max_retries}): {path_str}")

    @staticmethod
    def _unpack_result(result) -> Tuple[bool, Optional[str]]:
        if isinstance(result, tuple):
            return result[0], result[1] if len(result) > 1 else None
        return bool(result), None

    def _is_file_stable(self, file_path: Path) -> bool:
        """Check whether the file size is stable for a short interval."""
        if not file_path.exists():
            return False
        try:
            initial_size = file_path.stat().st_size
            time.sleep(1)
            if not file_path.exists():
                return False
            current_size = file_path.stat().st_size
            return current_size == initial_size
        except (FileNotFoundError, PermissionError) as e:
            logger.debug(f"Error checking file stability: {e}")
            return False
