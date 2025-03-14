"""Main application module."""
import os
import argparse
import time
from typing import List
from dotenv import load_dotenv

from .api import TVDBClient
from .cache import Cache
from .config import Config
from .renamer import FileRenamer
from .file_monitor import FileMonitor

class ShowRenamerApp:
    def __init__(self,
                 api_key: str,
                 watch_paths: List[str],
                 config_dir: str = "~/.config/showrenamer",
                 interactive: bool = True,
                 preview: bool = True,
                 cache_ttl_days: int = 7):
        self.config = Config(config_dir)
        self.cache = Cache(
            os.path.join(self.config.config_dir, self.config.config_files['cache']),
            cache_ttl_days
        )
        self.api_client = TVDBClient(api_key)
        self.renamer = FileRenamer(
            self.api_client,
            self.cache,
            self.config,
            interactive,
            preview
        )
        self.monitor = FileMonitor(
            watch_paths,
            self.renamer.process_file,
            self.renamer.video_extensions
        )

    def run(self):
        """Run the application."""
        try:
            print("Starting file monitor...")
            self.monitor.start()
            
            while True:
                self.monitor.retry_pending_files()
                time.sleep(3600)  # Check pending files every hour
                
        except KeyboardInterrupt:
            print("\nStopping file monitor...")
            self.monitor.stop()

def main():
    # Load environment variables from .env file
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Show Renamer - Automatically rename TV show files")
    parser.add_argument("paths", nargs="+", help="Paths to monitor for new files")
    parser.add_argument("--api-key", help="TVDB API key (can also be set via TVDB_API_KEY env variable)")
    parser.add_argument("--config-dir", default="~/.config/showrenamer", help="Configuration directory")
    parser.add_argument("--no-interactive", action="store_true", help="Don't ask for confirmation")
    parser.add_argument("--no-preview", action="store_true", help="Don't show preview of changes")
    parser.add_argument("--cache-ttl", type=int, default=7, help="Cache TTL in days")
    
    args = parser.parse_args()
    
    # Get API key from command line or environment variable
    api_key = args.api_key or os.getenv('TVDB_API_KEY')
    if not api_key:
        parser.error("TVDB API key is required. Provide it via --api-key or set TVDB_API_KEY environment variable")
    
    app = ShowRenamerApp(
        api_key=api_key,
        watch_paths=args.paths,
        config_dir=args.config_dir,
        interactive=not args.no_interactive,
        preview=not args.no_preview,
        cache_ttl_days=args.cache_ttl
    )
    
    app.run()

if __name__ == "__main__":
    main()
