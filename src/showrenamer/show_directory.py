"""Show directory management module."""
from pathlib import Path
from typing import List, Optional, Dict
import logging

logger = logging.getLogger(__name__)

class ShowDirectory:
    def __init__(self, base_directories: List[str]):
        """Initialize with a list of base directories to search for show folders."""
        self.base_directories = [Path(d) for d in base_directories]

    def find_show_directory(self, show_name: str) -> Optional[Path]:
        """Find the directory containing a show with the exact name."""
        for base_dir in self.base_directories:
            if not base_dir.exists():
                continue
            
            # Look for exact match directory
            show_dir = base_dir / show_name
            if show_dir.exists() and show_dir.is_dir():
                return show_dir
        
        return None

    def get_season_directory(self, show_dir: Path, season_number: int) -> Path:
        """Get the path to a season directory, creating it if it doesn't exist."""
        if season_number == 0:
            season_name = "Specials"
        else:
            season_name = f"Season {season_number:02d}"
        
        return show_dir / season_name

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
            logger.debug(f"No directory found for show: {show_name}")
            return None

        # Get season directory
        season_dir = self.get_season_directory(show_dir, season_number)
        if not season_dir.exists():
            logger.debug(f"Season directory doesn't exist: {season_dir}")
            return None
            
        return season_dir
        
    def move_file(self, source_file: Path, show_name: str, season_number: int) -> bool:
        """Move a file to the appropriate show and season directory if possible.
        
        Args:
            source_file: Path to the source file
            show_name: Name of the show
            season_number: Season number (0 for Specials)
            
        Returns:
            bool: True if file was moved successfully, False otherwise
        """
        # Get the target directory
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
            
            # Move the file
            source_file.rename(dest_file)
            logger.info(f"Moved {source_file} to {dest_file}")
            return True
        except Exception as e:
            logger.error(f"Error moving file {source_file} to {dest_file}: {e}")
            return False
