"""Main application module."""
import os
import argparse
import time
from typing import List
from dotenv import load_dotenv
import logging

from api import TVDBClient
from cache import Cache
from config import Config
from renamer import FileRenamer
from file_monitor import FileMonitor

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ShowRenamerApp:
    def __init__(self,
                 api_key: str,
                 watch_paths: List[str],
                 config_dir: str = "~/.config/showrenamer",
                 interactive: bool = False,
                 cache_ttl_days: int = 7,
                 dry_run: bool = False,
                 rename_only: bool = False):
        self.config = Config(config_dir)
        self.cache = Cache(
            os.path.join(self.config.config_dir, self.config.config_files['cache']),
            cache_ttl_days
        )
        self.api_client = TVDBClient(api_key)
        
        # Get show directories from config
        show_directories = self.config.directories.get("show_directories", [])
        
        # Add environment-specified destination if provided
        dest_dir = os.getenv('TV_SHOWS_DEST')
        if dest_dir and dest_dir not in show_directories:
            show_directories.append(dest_dir)
            self.config.directories["show_directories"] = show_directories
            self.config.save_directories(self.config.directories)
        
        if not show_directories:
            logger.warning("No show directories configured. Files will be renamed in place.")
        
        # Create log directory in config dir
        log_dir = os.path.join(self.config.config_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        
        self.renamer = FileRenamer(
            self.api_client,
            self.cache,
            self.config,
            show_directories,
            interactive,
            dry_run=dry_run,
            rename_only=rename_only,
            log_dir=log_dir
        )
        self.monitor = FileMonitor(
            watch_paths,
            self.renamer.process_file,
            self.renamer.video_extensions
        )

    def run(self):
        """Run the application."""
        try:
            # Log operation mode
            if self.renamer.dry_run:
                logger.info("=== DRY RUN MODE - NO CHANGES WILL BE MADE ===")
            
            logger.info("Starting file monitor...")
            logger.info(f"Show directories: {self.config.directories['show_directories']}")
            logger.info("File processing will begin after 3 minutes of stability")
            
            # Start the file monitor
            self.monitor.start()
            
            # Process existing files in monitored directories
            logger.info("Scanning for existing files in monitored directories...")
            self.monitor.process_existing_files()
            
            # Keep the main thread alive
            while True:
                time.sleep(60)
                
        except KeyboardInterrupt:
            logger.info("\nStopping file monitor...")
            self.monitor.stop()

def main():
    parser = argparse.ArgumentParser(description="Show Renamer - Automatically rename TV show files")
    parser.add_argument("paths", nargs="+", help="Paths to monitor for new files")
    parser.add_argument("--api-key", help="TVDB API key (can also be set via TVDB_API_KEY env variable)")
    parser.add_argument("--config-dir", default="~/.config/showrenamer", help="Configuration directory")
    parser.add_argument("--interactive", action="store_true", help="Enable interactive mode with confirmations")
    parser.add_argument("--cache-ttl", type=int, default=7, help="Cache TTL in days")
    parser.add_argument("--show-dir", action="append", help="Add a show directory to search for existing shows")
    
    # Operation mode options
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--enable-changes", action="store_true", help="Enable actual file changes (requires SHOWRENAMER_ENABLE_CHANGES=true)")
    mode_group.add_argument("--rename-only", action="store_true", help="Only rename files in place, don't move them")
    
    # Parse arguments first to get config_dir
    args = parser.parse_args()
    
    # Expand config_dir path
    config_dir = os.path.expanduser(args.config_dir)
    
    # Load environment variables from .env file in both current directory and config directory
    load_dotenv()
    config_env_path = os.path.join(config_dir, '.env')
    if os.path.exists(config_env_path):
        load_dotenv(config_env_path)
    
    # Args were already parsed above
    
    # Get API key from command line or environment variable
    api_key = args.api_key or os.getenv('TVDB_API_KEY')
    if not api_key:
        parser.error("TVDB API key is required. Provide it via --api-key or set TVDB_API_KEY environment variable")
    
    # Handle show directories configuration
    config = Config(args.config_dir)
    
    # If --show-dir is specified, add those directories
    if args.show_dir:
        show_dirs = config.directories.get("show_directories", [])
        for dir_path in args.show_dir:
            if dir_path not in show_dirs:
                show_dirs.append(dir_path)
        config.directories["show_directories"] = show_dirs
        config.save_directories(config.directories)
    
    # Check if changes are enabled via environment variable
    changes_enabled = os.getenv('SHOWRENAMER_ENABLE_CHANGES', '').lower() in ('true', '1', 'yes')
    if args.enable_changes and not changes_enabled:
        parser.error("SHOWRENAMER_ENABLE_CHANGES must be set to 'true' to enable actual file changes")

    # Determine operation mode
    dry_run = not (args.enable_changes and changes_enabled)  # Dry run by default unless changes explicitly enabled
    rename_only = args.rename_only or os.getenv('SHOWRENAMER_RENAME_ONLY', '').lower() in ('true', '1', 'yes')
    interactive = args.interactive or os.getenv('SHOWRENAMER_INTERACTIVE', '').lower() in ('true', '1', 'yes')
    
    if dry_run and rename_only:
        logger.warning("Both dry-run and rename-only modes specified. Using dry-run mode.")
        rename_only = False
    
    app = ShowRenamerApp(
        api_key=api_key,
        watch_paths=args.paths,
        config_dir=args.config_dir,
        interactive=interactive,
        preview=preview,
        cache_ttl_days=args.cache_ttl,
        dry_run=dry_run,
        rename_only=rename_only
    )
    
    app.run()

if __name__ == "__main__":
    main()
