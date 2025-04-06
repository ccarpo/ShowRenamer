"""File monitoring module."""
from pathlib import Path
from typing import Set, Dict, List, Callable
from datetime import datetime, timedelta
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class FileMonitor(FileSystemEventHandler):
    def __init__(self, 
                 watch_paths: List[str], 
                 file_handler: Callable,
                 video_extensions: Set[str],
                 retry_interval: int = 86400):  # 24 hours in seconds
        self.watch_paths = [Path(p).resolve() for p in watch_paths]
        self.file_handler = file_handler
        self.video_extensions = video_extensions
        self.retry_interval = retry_interval
        self.pending_files: Dict[str, datetime] = {}
        self.observer = Observer()

    def start(self):
        """Start monitoring directories."""
        for path in self.watch_paths:
            self.observer.schedule(self, str(path), recursive=True)
        self.observer.start()

    def stop(self):
        """Stop monitoring directories."""
        self.observer.stop()
        self.observer.join()

    def on_created(self, event):
        """Handle file creation events."""
        if not event.is_directory:
            file_path = Path(event.src_path)
            if file_path.suffix.lower() in self.video_extensions:
                self._process_file(file_path)

    def on_modified(self, event):
        """Handle file modification events."""
        if not event.is_directory:
            file_path = Path(event.src_path)
            if file_path.suffix.lower() in self.video_extensions:
                self._process_file(file_path)

    def _process_file(self, file_path: Path):
        """Process a video file."""
        try:
            success = self.file_handler(str(file_path))
            if not success:
                self.pending_files[str(file_path)] = datetime.now()
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
            self.pending_files[str(file_path)] = datetime.now()

    def retry_pending_files(self):
        """Retry processing of pending files."""
        now = datetime.now()
        retry_files = []
        
        for file_path, last_attempt in self.pending_files.items():
            if now - last_attempt >= timedelta(seconds=self.retry_interval):
                retry_files.append(file_path)
        
        for file_path in retry_files:
            try:
                success = self.file_handler(file_path)
                if success:
                    del self.pending_files[file_path]
                else:
                    self.pending_files[file_path] = now
            except Exception as e:
                print(f"Error retrying {file_path}: {e}")
                self.pending_files[file_path] = now
