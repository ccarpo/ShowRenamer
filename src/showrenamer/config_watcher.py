"""Configuration file watcher module."""
import os
import time
import logging
from typing import Callable, Dict
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

logger = logging.getLogger(__name__)

class ConfigFileHandler(FileSystemEventHandler):
    """Handler for configuration file change events."""
    
    def __init__(self, config_files: Dict[str, str], callback: Callable[[str], None]):
        """
        Initialize the config file handler.
        
        Args:
            config_files: Dictionary mapping config types to filenames
            callback: Function to call when a config file changes
        """
        self.config_files = config_files
        self.callback = callback
        self.last_modified_times = {}
        self.debounce_period = 1  # seconds
        
    def on_modified(self, event):
        """Handle file modification events."""
        if not isinstance(event, FileModifiedEvent):
            return
            
        # Get the filename from the path
        filename = os.path.basename(event.src_path)
        
        # Check if this is a config file we're monitoring
        config_type = None
        for cfg_type, cfg_file in self.config_files.items():
            if filename == cfg_file:
                config_type = cfg_type
                break
                
        if config_type:
            current_time = time.time()
            last_time = self.last_modified_times.get(config_type, 0)
            
            # Debounce to avoid multiple reloads for the same file change
            if current_time - last_time > self.debounce_period:
                logger.info(f"Configuration file changed: {filename}")
                self.last_modified_times[config_type] = current_time
                self.callback(config_type)


class ConfigWatcher:
    """Watches configuration files for changes and reloads them."""
    
    def __init__(self, config_dir: str, config_files: Dict[str, str], reload_callback: Callable[[str], None]):
        """
        Initialize the configuration watcher.
        
        Args:
            config_dir: Directory containing configuration files
            config_files: Dictionary mapping config types to filenames
            reload_callback: Function to call when a config file changes
        """
        self.config_dir = config_dir
        self.config_files = config_files
        self.reload_callback = reload_callback
        self.observer = None
        
    def start(self):
        """Start watching configuration files."""
        event_handler = ConfigFileHandler(self.config_files, self.reload_callback)
        self.observer = Observer()
        self.observer.schedule(event_handler, self.config_dir, recursive=False)
        self.observer.start()
        logger.info(f"Started watching configuration files in {self.config_dir}")
        
    def stop(self):
        """Stop watching configuration files."""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            logger.info("Stopped watching configuration files")
