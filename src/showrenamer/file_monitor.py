"""File monitoring module."""
from pathlib import Path
from typing import Set, List, Callable
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import logging

from showrenamer.scheduler import Scheduler

logger = logging.getLogger(__name__)


class FileMonitor(FileSystemEventHandler):
    """Watchdog-based file monitor that delegates scheduling to the Scheduler."""

    def __init__(self,
                 watch_paths: List[str],
                 file_handler: Callable,
                 video_extensions: Set[str],
                 retry_interval: int = 86400,
                 stability_period: int = 300,
                 full_rescan_interval: int = 1800,
                 no_target_dir_retry_interval: int = 60,
                 max_retries: int = 3):
        self.watch_paths = [Path(p).resolve() for p in watch_paths]
        self.video_extensions = video_extensions
        self.scheduler = Scheduler(
            file_handler=file_handler,
            watch_paths=watch_paths,
            video_extensions=video_extensions,
            stability_period=stability_period,
            retry_interval=retry_interval,
            full_rescan_interval=full_rescan_interval,
            no_target_dir_retry_interval=no_target_dir_retry_interval,
            max_retries=max_retries
        )
        self.observer = Observer()

    def start(self):
        """Start monitoring directories and the scheduler."""
        for path in self.watch_paths:
            if path.exists() and path.is_dir():
                self.observer.schedule(self, str(path), recursive=True)
            else:
                logger.warning(f"Watch path does not exist or is not a directory: {path}")
        self.observer.start()
        self.scheduler.start()

    def stop(self):
        """Stop monitoring directories and the scheduler."""
        self.scheduler.stop()
        self.observer.stop()
        self.observer.join()

    def process_existing_files(self):
        """Trigger a full re-scan of all monitored directories."""
        self.scheduler.schedule_full_rescan()

    def force_retry_pending_files(self):
        """Immediately retry pending files and re-scan all directories.

        This is used by the show-directory watcher when a new show folder is
        created, because previously failed moves may now succeed.
        """
        self.scheduler.schedule_config_rescan()

    def update_watch_paths(self, watch_paths: List[str]):
        """Replace the set of watched paths and reschedule a re-scan."""
        self.watch_paths = [Path(p).resolve() for p in watch_paths]
        self.scheduler.update_watch_paths(watch_paths)

        self.observer.stop()
        self.observer.join()
        self.observer = Observer()
        for path in self.watch_paths:
            if path.exists() and path.is_dir():
                self.observer.schedule(self, str(path), recursive=True)
            else:
                logger.warning(f"Watch path does not exist or is not a directory: {path}")
        self.observer.start()
        self.scheduler.schedule_full_rescan()

    def on_created(self, event):
        """Handle file creation events."""
        if not event.is_directory:
            file_path = Path(event.src_path)
            if file_path.suffix.lower() in self.video_extensions:
                logger.debug(f"File created: {file_path}")
                self.scheduler.add_file(file_path)

    def on_modified(self, event):
        """Handle file modification events."""
        if not event.is_directory:
            file_path = Path(event.src_path)
            if file_path.suffix.lower() in self.video_extensions:
                logger.debug(f"File modified: {file_path}")
                self.scheduler.add_file(file_path)

    def on_moved(self, event):
        """Handle file move events."""
        if not event.is_directory:
            if event.src_path:
                self.scheduler.remove_file(Path(event.src_path))
            if event.dest_path:
                dest = Path(event.dest_path)
                if dest.suffix.lower() in self.video_extensions:
                    logger.debug(f"File moved to: {dest}")
                    self.scheduler.add_file(dest)

    def on_deleted(self, event):
        """Handle file deletion events by removing from queues."""
        if not event.is_directory:
            self.scheduler.remove_file(Path(event.src_path))
