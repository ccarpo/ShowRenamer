"""Show directory management module."""
from pathlib import Path
from typing import List, Optional, Dict, Callable
import logging
import re
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)

class ShowDirectory:
    def __init__(self, base_directories: List[str]):
        """Initialize with a list of base directories to search for show folders."""
        self.base_directories = [Path(d) for d in base_directories]

    def normalize_name(self, name: str) -> str:
        """Normalize a name by replacing special characters.
        
        This helps with matching show names to directory names when they contain
        special characters like colons (:) that might be replaced in directory names.
        Hyphens (-) can be either replaced by ' - ' or removed entirely.
        """
        # Replace common special characters with standard replacements
        normalized = re.sub(r'[\\/*?"<>|:]', '', name)
        # Normalize whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # Create variants for hyphen handling
        variants = [normalized]
        
        # Variant 1: Replace hyphens with spaced hyphens
        if '-' in normalized:
            spaced_hyphens = re.sub(r'\s*-\s*', ' - ', normalized)
            variants.append(spaced_hyphens)
            
        # Variant 2: Remove hyphens entirely
        if '-' in normalized:
            no_hyphens = re.sub(r'\s*-\s*', ' ', normalized)
            no_hyphens = re.sub(r'\s+', ' ', no_hyphens).strip()
            variants.append(no_hyphens)
            
        return variants
        
    def find_show_directory(self, show_name: str) -> Optional[Path]:
        """Find the directory containing a show with the exact or normalized name.
        
        Handles different variants of the show name, particularly with respect to hyphens
        which can be formatted as ' - ' or removed entirely.
        """
        for base_dir in self.base_directories:
            if not base_dir.exists():
                continue
            
            # Try exact match first
            show_dir = base_dir / show_name
            if show_dir.exists() and show_dir.is_dir():
                return show_dir
                
            # Try all normalized variants
            name_variants = self.normalize_name(show_name)
            
            # Try each variant as an exact directory name
            for variant in name_variants:
                if variant != show_name:  # Already tried the original name
                    show_dir = base_dir / variant
                    if show_dir.exists() and show_dir.is_dir():
                        logger.info(f"Found directory using normalized variant: '{variant}' for show '{show_name}'.") 
                        return show_dir
            
            # If that fails too, try to find a directory with similar name
            if base_dir.exists() and base_dir.is_dir():
                for dir_path in base_dir.iterdir():
                    if dir_path.is_dir():
                        # Get normalized variants of the directory name
                        dir_variants = self.normalize_name(dir_path.name)
                        
                        # Check if any show name variant matches any directory name variant
                        for show_variant in name_variants:
                            for dir_variant in dir_variants:
                                if show_variant == dir_variant:
                                    logger.info(f"Found directory with similar name: '{dir_path.name}' for show '{show_name}'.") 
                                    return dir_path
        
        return None

    def get_season_directory(self, show_dir: Path, season_number: int) -> Path:
        """Get the path to a season directory, creating it if it doesn't exist.
        
        Tries to determine the naming convention used in the show directory by checking
        for existing season folders. First checks for folders without leading zeros,
        then checks for folders with leading zeros. If no existing season folders are found,
        defaults to creating a folder without leading zeros.
        """
        if season_number == 0:
            season_name = "Specials"
            return show_dir / season_name

        # First format: "Season X" (no leading zeros)
        no_leading_zeros = f"Season {season_number}"
        # Second format: "Season XX" (with leading zeros)
        with_leading_zeros = f"Season {season_number:02d}"
        
        # Check if the specific season directory already exists in either format
        if (show_dir / no_leading_zeros).exists():
            return show_dir / no_leading_zeros
        if (show_dir / with_leading_zeros).exists():
            return show_dir / with_leading_zeros
            
        # If the specific season doesn't exist, determine format from other seasons
        # First check if any season directories without leading zeros exist
        test_dir = show_dir / f"Season 1"
        if test_dir.exists() and test_dir.is_dir():
            logger.debug(f"Found season directory without leading zeros: {test_dir}")
            return show_dir / no_leading_zeros
        
        # Then check if any season directories with leading zeros exist
        test_dir = show_dir / f"Season 01"
        if test_dir.exists() and test_dir.is_dir():
            logger.debug(f"Found season directory with leading zeros: {test_dir}")
            return show_dir / with_leading_zeros
        
        # If no existing season directories found, default to no leading zeros
        logger.debug(f"No existing season directories found, using format without leading zeros")
        return show_dir / no_leading_zeros

    def can_move_file(self, source_file: Path, dest_file: Path) -> Dict[str, bool]:
        """Check if a file can be moved to the destination.
        
        Returns:
            Dict with keys:
            - can_move: Whether the file can be moved
            - dest_exists: Whether the destination file already exists
            - parent_exists: Whether the parent directory exists
        """
        result = {
            "can_move": False,
            "dest_exists": False,
            "parent_exists": False
        }

        # Check if destination already exists
        if dest_file.exists():
            result["dest_exists"] = True
            logger.warning(f"Destination file already exists: {dest_file}")
            return result

        # Check if parent directory exists
        if not dest_file.parent.exists():
            result["parent_exists"] = False
            logger.warning(f"Parent directory doesn't exist: {dest_file.parent}")
            return result

        result["parent_exists"] = True
        result["can_move"] = True
        return result

    def get_target_directory(self, show_name: str, season_number: int) -> Optional[Path]:
        """Get the target directory where a file would be moved to.
        
        Args:
            show_name: Name of the show
            season_number: Season number (0 for Specials)
            
        Returns:
            Optional[Path]: Path to the target directory, or None if not found
        """
        # Find show directory
        show_dir = self.find_show_directory(show_name)
        if not show_dir:
            logger.info("Found show directory: None")
            logger.debug(f"No directory found for show: {show_name}")
            return None
        logger.info(f"Found show directory: {show_dir}")

        # Get season directory
        season_dir = self.get_season_directory(show_dir, season_number)
        if not season_dir.exists():
            logger.info(f"Creating season directory: {season_dir}")
            season_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Using season directory: {season_dir}")

        return season_dir
        
    def move_file(self, source_file: Path, show_name: str, season_number: int, season_dir: Optional[Path] = None) -> bool:
        """Move a file to the appropriate show and season directory if possible.
        
        Args:
            source_file: Path to the source file
            show_name: Name of the show
            season_number: Season number (0 for Specials)
            season_dir: Optional precomputed season directory
            
        Returns:
            bool: True if file was moved successfully, False otherwise
        """
        # Get the target directory
        if season_dir is None:
            season_dir = self.get_target_directory(show_name, season_number)
        if not season_dir:
            return False

        # Prepare destination path
        dest_file = season_dir / source_file.name

        # Check if we can move the file
        move_check = self.can_move_file(source_file, dest_file)
        if not move_check["can_move"]:
            return False

        try:
            # Create parent directories if they don't exist
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            
            try:
                # First try a direct move (rename) which is faster but only works on same filesystem
                source_file.rename(dest_file)
                logger.info(f"Moved to {dest_file}")
                return True
            except OSError as e:
                # If we get a cross-device link error, fall back to copy and delete
                if e.errno == 18:  # EXDEV error (Invalid cross-device link)
                    logger.info(f"Cross-filesystem move detected, using copy+delete for {source_file}")
                    import shutil
                    
                    # Copy the file
                    shutil.copy2(source_file, dest_file)
                    
                    # Verify the copy was successful by checking file sizes
                    if source_file.stat().st_size == dest_file.stat().st_size:
                        # Delete the original file
                        source_file.unlink()
                        logger.info(f"Copied and deleted to {dest_file}")
                        return True
                    else:
                        # Copy was incomplete, remove the partial file
                        if dest_file.exists():
                            dest_file.unlink()
                        logger.error(f"Copy verification failed for {source_file} to {dest_file}")
                        return False
                else:
                    # Re-raise if it's not a cross-device link error
                    raise
        except Exception as e:
            logger.error(f"Error moving file {source_file} to {dest_file}: {e}")
            return False


class ShowDirectoryWatcher(FileSystemEventHandler):
    """Watch show directories for newly created folders and trigger a callback."""

    def __init__(self, show_directories: List[str], on_directory_created: Callable[[], None]):
        """
        Initialize the show directory watcher.

        Args:
            show_directories: List of base directories containing show folders
            on_directory_created: Callback to invoke when a new directory is created
        """
        self.show_directories = [Path(d) for d in show_directories if d]
        self.on_directory_created = on_directory_created
        self.observer = Observer()
        self._started = False

    def start(self):
        """Start watching show directories for new folders."""
        for d in self.show_directories:
            if d.exists() and d.is_dir():
                try:
                    self.observer.schedule(self, str(d), recursive=False)
                    logger.info(f"Watching show directory for new folders: {d}")
                except Exception as e:
                    logger.warning(f"Could not watch show directory {d}: {e}")
        self.observer.start()
        self._started = True

    def on_created(self, event):
        """Handle new directory creation events."""
        if event.is_directory:
            logger.info(f"New directory created in show library: {event.src_path}")
            self.on_directory_created()

    def update_directories(self, show_directories: List[str]):
        """Update the watched directories (e.g., after configuration change)."""
        if not self._started:
            self.show_directories = [Path(d) for d in show_directories if d]
            return

        self.observer.stop()
        self.observer.join()
        self.observer = Observer()
        self.show_directories = [Path(d) for d in show_directories if d]
        self.start()

    def stop(self):
        """Stop watching show directories."""
        if self._started:
            self.observer.stop()
            self.observer.join()
            self._started = False
            logger.info("Stopped watching show directories")
