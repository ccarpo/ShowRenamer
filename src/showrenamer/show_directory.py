"""Show directory management module."""
from pathlib import Path
from typing import List, Optional, Dict
import logging
import re

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
        logger.info(f"Found show directory: {show_dir}")
        if not show_dir:
            logger.debug(f"No directory found for show: {show_name}")
            return None

        # Get season directory
        season_dir = self.get_season_directory(show_dir, season_number)
        logger.info(f"Found season directory: {season_dir}")
        if not season_dir.exists():
            logger.info(f"Creating season directory: {season_dir}")
            season_dir.mkdir(parents=True, exist_ok=True)
            
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
