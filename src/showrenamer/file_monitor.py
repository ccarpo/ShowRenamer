"""File monitoring module."""
from pathlib import Path
from typing import Set, Dict, List, Callable, Optional
from datetime import datetime, timedelta
import time
import threading
import logging
import re
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)

class FileMonitor(FileSystemEventHandler):
    def __init__(self, 
                 watch_paths: List[str], 
                 file_handler: Callable,
                 video_extensions: Set[str],
                 retry_interval: int = 86400,  # 24 hours in seconds
                 stability_period: int = 300):  # 5 minutes in seconds
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
                        # Check if this file looks like it's already been renamed but not moved
                        # Files that have been renamed typically have a standard format like "Show Name - S01E01 - Episode Title.ext"
                        if re.search(r' - S\d+E\d+', file_path.name):
                            logger.info(f"Found existing renamed file, adding to pending list for retry: {file_path}")
                            self.pending_files[str(file_path)] = datetime.now() - timedelta(seconds=self.retry_interval)
                        else:
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
        if not event.is_directory:
            # Remove the old source path from queues
            if event.src_path:
                src = Path(event.src_path)
                with self.processing_lock:
                    self.changed_files.pop(str(src), None)
                    self.pending_files.pop(str(src), None)
            # Track the destination if it's a video file
            if event.dest_path:
                dest = Path(event.dest_path)
                if dest.suffix.lower() in self.video_extensions:
                    logger.debug(f"File moved to: {dest}")
                    self._add_to_changed_files(dest)

    def on_deleted(self, event):
        """Handle file deletion events by removing from queues."""
        if not event.is_directory:
            path = Path(event.src_path)
            with self.processing_lock:
                removed_cf = self.changed_files.pop(str(path), None)
                removed_pf = self.pending_files.pop(str(path), None)
            if removed_cf or removed_pf:
                logger.debug(f"File deleted, removed from queues: {path}")

    def _add_to_changed_files(self, file_path: Path):
        """Add a file to the changed files list and update the last change time."""
        with self.processing_lock:
            self.changed_files[str(file_path)] = datetime.now()
            self.last_change_time = datetime.now()
    
    def _file_processor_loop(self):
        """Background thread that processes files after a period of stability."""
        # Flag to track if we've done an initial processing
        initial_processing_done = False
        last_processing_time = None
        
        while not self.stop_event.is_set():
            process_now = False
            files_to_process = []
            
            with self.processing_lock:
                # Cleanup: remove any non-existent files from the changed_files queue
                if self.changed_files:
                    cleanup_keys = [k for k in list(self.changed_files.keys()) if not Path(k).exists()]
                    for k in cleanup_keys:
                        logger.info(f"Cleanup: removing non-existent file from queue: {k}")
                        self.changed_files.pop(k, None)
                # Case 1: Initial startup - set a timestamp to process files after stability period
                if not initial_processing_done and self.last_change_time is None:
                    self.last_change_time = datetime.now()
                    initial_processing_done = True
                    time.sleep(1)
                    continue
                
                # Case 2: Check if stability period has elapsed since last change
                if self.last_change_time is not None:
                    now = datetime.now()
                    time_since_last_change = (now - self.last_change_time).total_seconds()
                    
                    if time_since_last_change >= self.stability_period:
                        # Stability period has elapsed, process any files
                        process_now = True
                        files_to_process = list(self.changed_files.keys())
                
                # Case 3: Periodic check for any unprocessed files even when no new changes
                if not process_now and self.changed_files:
                    now = datetime.now()
                    # If we haven't processed files in a while, do it now
                    if last_processing_time is None or (now - last_processing_time).total_seconds() >= self.stability_period:
                        process_now = True
                        files_to_process = list(self.changed_files.keys())
            
            if not process_now:
                time.sleep(1)
                continue
                
            if files_to_process:
                logger.info(f"Processing {len(files_to_process)} files")
                last_processing_time = datetime.now()
                
                # Check if files are still being modified (e.g., still being copied/unzipped)
                stable_files = []
                for file_path_str in files_to_process:
                    file_path = Path(file_path_str)
                    # If the file no longer exists, remove it from queue
                    if not file_path.exists():
                        logger.info(f"File no longer exists, removing from queue: {file_path}")
                        with self.processing_lock:
                            if file_path_str in self.changed_files:
                                del self.changed_files[file_path_str]
                        continue
                    if not self._is_file_stable(file_path):
                        logger.info(f"File still being modified, deferring: {file_path}")
                        continue
                    stable_files.append(file_path_str)
                
                # Process only stable files
                for file_path_str in stable_files:
                    self._process_file(Path(file_path_str))
                    # Remove processed files from the changed_files dict
                    with self.processing_lock:
                        if file_path_str in self.changed_files:
                            del self.changed_files[file_path_str]
                
                # If we still have unstable files, don't reset the last_change_time
                with self.processing_lock:
                    if not self.changed_files:
                        self.last_change_time = None
            
            # Also check for any pending files that need retry
            self.retry_pending_files()
            
            # Sleep a bit before checking again
            time.sleep(5)
    
    def _is_file_stable(self, file_path: Path) -> bool:
        """Check if a file is stable (not being modified)."""
        if not file_path.exists():
            return False
            
        try:
            # Get initial file size
            initial_size = file_path.stat().st_size
            # Wait a short time
            time.sleep(1)
            # Check if file size has changed
            if file_path.exists():
                current_size = file_path.stat().st_size
                if current_size != initial_size:
                    logger.debug(f"File size changed from {initial_size} to {current_size}: {file_path}")
                    return False
                return True
            return False
        except (FileNotFoundError, PermissionError) as e:
            logger.debug(f"Error checking file stability: {e}")
            return False
    
    def _process_file(self, file_path: Path):
        """Process a video file."""
        try:
            # Final check to ensure file exists and is accessible
            if not file_path.exists():
                logger.warning(f"File no longer exists: {file_path}")
                return

            logger.info(f"Processing file: {file_path}")
            result = self.file_handler(str(file_path))
            if isinstance(result, tuple):
                success, reason = result
            else:
                success, reason = (bool(result), None)
            if not success:
                msg = f"Failed to process file: {file_path}"
                if reason:
                    msg += f". Reason: {reason}"
                logger.warning(msg)
                self.pending_files[str(file_path)] = datetime.now()
        except Exception as e:
            logger.error(f"Error processing {file_path}: {e}")
            self.pending_files[str(file_path)] = datetime.now()

    def retry_pending_files(self):
        """Retry processing of pending files."""
        now = datetime.now()
        retry_files = []
        files_to_remove = []
        
        # First, check all pending files and remove those that no longer exist
        for file_path, last_attempt in list(self.pending_files.items()):
            path_obj = Path(file_path)
            if not path_obj.exists():
                # File no longer exists (likely moved successfully), remove from pending
                files_to_remove.append(file_path)
                logger.info(f"Removing non-existent file from pending list: {file_path}")
            elif now - last_attempt >= timedelta(seconds=self.retry_interval):
                # File exists and is due for retry
                retry_files.append(file_path)
        
        # Remove non-existent files from pending list
        for file_path in files_to_remove:
            del self.pending_files[file_path]
        
        if retry_files:
            logger.info(f"Retrying {len(retry_files)} pending files")
            
        for file_path in retry_files:
            try:
                # Double-check file still exists before processing
                if not Path(file_path).exists():
                    logger.info(f"File no longer exists, removing from pending: {file_path}")
                    del self.pending_files[file_path]
                    continue
                    
                success = self.file_handler(file_path)
                if success:
                    del self.pending_files[file_path]
                else:
                    self.pending_files[file_path] = now
            except Exception as e:
                logger.error(f"Error retrying {file_path}: {e}")
                self.pending_files[file_path] = now
