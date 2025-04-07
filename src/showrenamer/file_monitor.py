"""File monitoring module."""
from pathlib import Path
from typing import Set, Dict, List, Callable, Optional
from datetime import datetime, timedelta
import time
import threading
import logging
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)

class FileMonitor(FileSystemEventHandler):
    def __init__(self, 
                 watch_paths: List[str], 
                 file_handler: Callable,
                 video_extensions: Set[str],
                 retry_interval: int = 86400,  # 24 hours in seconds
                 stability_period: int = 10):  # 3 minutes in seconds
        self.watch_paths = [Path(p).resolve() for p in watch_paths]
        self.file_handler = file_handler
        self.video_extensions = video_extensions
        self.retry_interval = retry_interval
        self.stability_period = stability_period
        self.pending_files: Dict[str, datetime] = {}
        self.changed_files: Dict[str, datetime] = {}
        self.last_change_time: Optional[datetime] = None
        self.processing_lock = threading.Lock()
        self.observer = Observer()
        self.stop_event = threading.Event()
        self.processor_thread = None

    def start(self):
        """Start monitoring directories."""
        for path in self.watch_paths:
            self.observer.schedule(self, str(path), recursive=True)
        self.observer.start()
        
        # Start the file processor thread
        self.stop_event.clear()
        self.processor_thread = threading.Thread(target=self._file_processor_loop)
        self.processor_thread.daemon = True
        self.processor_thread.start()
        
    def process_existing_files(self):
        """Scan and process all existing video files in the monitored directories."""
        for watch_path in self.watch_paths:
            logger.info(f"Scanning for existing files in {watch_path}")
            path = Path(watch_path)
            if path.exists() and path.is_dir():
                # Find all video files recursively
                for file_path in path.glob('**/*'):
                    if file_path.is_file() and file_path.suffix.lower() in self.video_extensions:
                        logger.info(f"Found existing file: {file_path}")
                        self._add_to_changed_files(file_path)
            else:
                logger.warning(f"Watch path does not exist or is not a directory: {watch_path}")

    def stop(self):
        """Stop monitoring directories."""
        self.stop_event.set()
        if self.processor_thread:
            self.processor_thread.join(timeout=5)
        self.observer.stop()
        self.observer.join()

    def on_created(self, event):
        """Handle file creation events."""
        if not event.is_directory:
            file_path = Path(event.src_path)
            if file_path.suffix.lower() in self.video_extensions:
                logger.debug(f"File created: {file_path}")
                self._add_to_changed_files(file_path)

    def on_modified(self, event):
        """Handle file modification events."""
        if not event.is_directory:
            file_path = Path(event.src_path)
            if file_path.suffix.lower() in self.video_extensions:
                logger.debug(f"File modified: {file_path}")
                self._add_to_changed_files(file_path)
                
    def on_moved(self, event):
        """Handle file move events."""
        if not event.is_directory and event.dest_path:
            file_path = Path(event.dest_path)
            if file_path.suffix.lower() in self.video_extensions:
                logger.debug(f"File moved to: {file_path}")
                self._add_to_changed_files(file_path)

    def _add_to_changed_files(self, file_path: Path):
        """Add a file to the changed files list and update the last change time."""
        with self.processing_lock:
            self.changed_files[str(file_path)] = datetime.now()
            self.last_change_time = datetime.now()
    
    def _file_processor_loop(self):
        """Background thread that processes files after a period of stability."""
        while not self.stop_event.is_set():
            # Check if there have been any changes
            with self.processing_lock:
                if self.last_change_time is None:
                    # No changes detected yet
                    time.sleep(1)
                    continue
                
                # Check if the stability period has elapsed since the last change
                now = datetime.now()
                time_since_last_change = (now - self.last_change_time).total_seconds()
                
                if time_since_last_change < self.stability_period:
                    # Not stable yet, wait more
                    time.sleep(1)
                    continue
                
                # Stability period has elapsed, process the files
                files_to_process = list(self.changed_files.keys())
                self.changed_files.clear()
                self.last_change_time = None
            
            if files_to_process:
                logger.info(f"Processing {len(files_to_process)} files after {self.stability_period} seconds of stability")
                for file_path in files_to_process:
                    self._process_file(Path(file_path))
            
            # Also check for any pending files that need retry
            self.retry_pending_files()
            
            # Sleep a bit before checking again
            time.sleep(10)
    
    def _process_file(self, file_path: Path):
        """Process a video file."""
        try:
            logger.info(f"Processing file: {file_path}")
            success = self.file_handler(str(file_path))
            if not success:
                self.pending_files[str(file_path)] = datetime.now()
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            self.pending_files[str(file_path)] = datetime.now()

    def retry_pending_files(self):
        """Retry processing of pending files."""
        now = datetime.now()
        retry_files = []
        
        for file_path, last_attempt in list(self.pending_files.items()):
            if now - last_attempt >= timedelta(seconds=self.retry_interval):
                retry_files.append(file_path)
        
        if retry_files:
            logger.info(f"Retrying {len(retry_files)} pending files")
            
        for file_path in retry_files:
            try:
                success = self.file_handler(file_path)
                if success:
                    del self.pending_files[file_path]
                else:
                    self.pending_files[file_path] = now
            except Exception as e:
                logger.error(f"Error retrying {file_path}: {e}")
                self.pending_files[file_path] = now
