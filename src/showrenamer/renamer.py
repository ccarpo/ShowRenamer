"""File renaming module."""
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from fuzzywuzzy import fuzz
import logging

from showrenamer.show_directory import ShowDirectory
from showrenamer.file_logger import FileLogger

logger = logging.getLogger(__name__)

class FileRenamer:
    def __init__(self, 
                 api_client,
                 cache,
                 config,
                 show_directories: List[str],
                 interactive: bool = True,
                 dry_run: bool = True,  # Default to dry-run mode
                 rename_only: bool = False,
                 log_dir: str = None):
        self.api_client = api_client
        self.cache = cache
        self.config = config
        self.interactive = interactive
        self.dry_run = dry_run
        self.rename_only = rename_only
        self.show_directories = show_directories
        self.show_directory = ShowDirectory(show_directories)
        self.file_logger = FileLogger(log_dir)
        self.video_extensions = {
            '.mkv', '.avi', '.mp4', '.m4v', '.mov',
            '.wmv', '.flv', '.mpg', '.mpeg', '.m2ts'
        }

    def process_file(self, file_path: str) -> bool:
        """Process a single file for renaming."""
        path = Path(file_path)
        if not path.exists() or path.suffix.lower() not in self.video_extensions:
            return False

        parsed_info = self.parse_filename(path.name)
        if not parsed_info:
            return False

        show_name, season, episode = parsed_info
        series_info = self._get_series_info(show_name)
        if not series_info:
            return False

        episode_info = self._get_episode_info(series_info['id'], season, episode)
        if not episode_info:
            return False

        new_name = self._generate_new_filename(path, series_info, episode_info)
        if not new_name:
            return False

        # Get the show name from series info (prefer German title if available)
        show_name = series_info.get("translations", {}).get("deu") or series_info["name"]
        
        # Determine what operations to perform
        should_rename = True  # Always rename unless rename-only mode is active
        should_move = not self.rename_only  # Move unless rename-only mode
        
        # Check if episode has a name (either default or translated)
        has_episode_name = bool(episode_info.get("translations", {}).get("deu") or episode_info.get("name", ""))
        if not has_episode_name:
            logger.warning(f"No episode name found for {path.name}. Will rename but not move.")
            should_move = False
        
        # Check if we're in dry-run mode
        if self.dry_run:
            if should_rename:
                logger.info(f"[DRY RUN] Would rename: {path.name} -> {new_name}")
            if should_move:
                target_dir = self.show_directory.get_target_directory(show_name, episode_info["seasonNumber"])
                if target_dir:
                    logger.info(f"[DRY RUN] Would move to: {target_dir}")
                else:
                    logger.info(f"[DRY RUN] Would not move (no suitable target directory found)")
            
            if self.interactive and not self.dry_run:
                if not self._confirm_rename():
                    return False
            
            # In dry-run mode, always return success without making changes
            if self.dry_run:
                return True
        
        # Perform the actual operations
        new_path = path
        
        # First rename in place if needed
        if should_rename and not self.dry_run:
            new_path = path.parent / new_name
            try:
                path.rename(new_path)
                logger.info(f"Renamed: {path.name} -> {new_name}")
                # Log the rename operation
                self.file_logger.log_operation(
                    operation_type="rename",
                    source_file=path,
                    target_file=new_path,
                    details={
                        "show_name": show_name,
                        "season": episode_info["seasonNumber"],
                        "episode": episode_info["number"],
                        "episode_title": episode_info.get("name", "")
                    }
                )
            except Exception as e:
                logger.error(f"Error renaming file: {e}")
                # Log the failed operation
                self.file_logger.log_operation(
                    operation_type="rename",
                    source_file=path,
                    target_file=new_path,
                    success=False,
                    details={"error": str(e)}
                )
                return False

        # Then try to move to show directory if needed
        if should_move and not self.dry_run:
            target_dir = self.show_directory.get_target_directory(show_name, episode_info["seasonNumber"])
            moved = self.show_directory.move_file(new_path, show_name, episode_info["seasonNumber"])
            if moved:
                # Log the move operation
                self.file_logger.log_operation(
                    operation_type="move",
                    source_file=new_path,
                    target_file=target_dir / new_path.name if target_dir else None,
                    details={
                        "show_name": show_name,
                        "season": episode_info["seasonNumber"],
                        "episode": episode_info["number"]
                    }
                )
                return True
            else:
                logger.warning(f"File not moved: {new_path}")
                # Log the failed move operation
                self.file_logger.log_operation(
                    operation_type="move",
                    source_file=new_path,
                    target_file=target_dir / new_path.name if target_dir else None,
                    success=False,
                    details={
                        "show_name": show_name,
                        "season": episode_info["seasonNumber"],
                        "reason": "No suitable target directory found"
                    }
                )
                # Return False to indicate failure and trigger retry
                return False
        
        # If we only needed to rename or if we're in dry run mode, return success
        return True

    def parse_filename(self, filename: str) -> Optional[Tuple[str, int, int]]:
        """Extract show name, season, and episode from filename."""
        base_name = Path(filename).stem.lower()
        
        for pattern in self.config.patterns["patterns"]:
            match = re.search(pattern, base_name)
            if match:
                if len(match.groups()) == 3:
                    show_part = match.group(1)
                    season = int(match.group(2))
                    episode = int(match.group(3))
                else:
                    show_part = base_name[:match.start()]
                    season = int(match.group(1))
                    episode = int(match.group(2))
                
                clean_name = self._clean_show_name(show_part)
                return clean_name, season, episode
        
        return None

    def _clean_show_name(self, name: str) -> str:
        """Clean show name using configured patterns."""
        # Get strings to remove and sort by length (longest first)
        strings_to_remove = sorted(
            self.config.patterns.get("strings_to_remove", []),
            key=len,
            reverse=True
        )
        
        # Remove strings from the strings_to_remove list with case-insensitive matching
        for string_to_remove in strings_to_remove:
            # Use regex with case-insensitive flag to replace the string
            name = re.sub(re.escape(string_to_remove), "", name, flags=re.IGNORECASE)
    
        # Apply replacements
        if self.config.patterns["replacements"]["dots_to_spaces"]:
            name = name.replace(".", " ")
        if self.config.patterns["replacements"]["underscores_to_spaces"]:
            name = name.replace("_", " ")
        if self.config.patterns["replacements"]["dashes_to_spaces"]:
            name = name.replace("-", " ")
        
        # Clean up multiple spaces
        name = re.sub(r'\s+', ' ', name).strip()
        
        # Apply mapping if available
        return self.config.mapping.get(name, name)

    def update_show_directories(self, show_directories: List[str]):
        """Update the show directories used for moving files.
        
        Args:
            show_directories: List of directory paths to use for show directories
        """
        self.show_directories = show_directories
        self.show_directory = ShowDirectory(show_directories)
        logger.info(f"Updated show directories: {show_directories}")
        
    def update_patterns(self, patterns: Dict):
        """Update the patterns used for filename parsing.
        
        Args:
            patterns: Updated patterns configuration
        """
        logger.info("Patterns configuration updated")
        # No need to store patterns locally as we reference self.config.patterns
        
    def update_mapping(self, mapping: Dict):
        """Update the series name mapping.
        
        Args:
            mapping: Updated mapping configuration
        """
        logger.info("Series mapping configuration updated")
        # No need to store mapping locally as we reference self.config.mapping
        
    def _get_series_info(self, show_name: str) -> Optional[Dict]:
        """Get series information from cache or API."""
        cached_info = self.cache.get(f"series_{show_name}")
        if cached_info:
            return cached_info

        results = self.api_client.search_series(show_name)
        if not results:
            return None

        best_match = self._find_best_match(show_name, results)
        if best_match:
            self.cache.set(f"series_{show_name}", best_match)
            return best_match
        return None

    def _find_best_match(self, query: str, results: List[Dict]) -> Optional[Dict]:
        """Find best matching series from results."""
        best_match = None
        highest_ratio = 0

        for show in results:
            ratio_original = fuzz.ratio(query.lower(), show["name"].lower())
            german_title = show.get("translations", {}).get("deu")
            ratio_german = fuzz.ratio(query.lower(), german_title.lower()) if german_title else 0
            
            current_ratio = max(ratio_original, ratio_german)
            if current_ratio > highest_ratio:
                highest_ratio = current_ratio
                best_match = show

        if highest_ratio < 50:
            return None

        if self.interactive:
            confirm = input(f'Found series: {best_match["name"]} ({best_match.get("year", "N/A")}). '
                          f'Is this correct? (y/n): ').lower()
            if confirm != 'y':
                return None

        return best_match

    def _get_episode_info(self, series_id: int, season: int, episode: int) -> Optional[Dict]:
        """Get episode information from cache or API."""
        cache_key = f"episodes_{series_id}"
        episodes = self.cache.get(cache_key)
        refresh_cache = False
        
        if not episodes:
            refresh_cache = True
        else:
            # Check if we have the episode in cache but with missing information
            for ep in episodes:
                ep_num = ep.get("number") or ep.get("episodeNumber")
                if ep.get("seasonNumber") == season and ep_num == episode:
                    # Check if episode name is missing
                    has_name = bool(ep.get("name"))
                    has_translation = bool(ep.get("translations", {}).get("deu"))
                    
                    # Refresh cache if both names are missing
                    if not has_name and not has_translation:
                        logger.info(f"Episode S{season}E{episode} found in cache but missing name/translation. Refreshing from API.")
                        refresh_cache = True
                    break
        
        if refresh_cache:
            episodes = self.api_client.get_episode_info(series_id)
            self.cache.set(cache_key, episodes)

        for ep in episodes:
            # Check for both "number" and "episodeNumber" fields to handle API inconsistencies
            ep_num = ep.get("number") or ep.get("episodeNumber")
            if ep.get("seasonNumber") == season and ep_num == episode:
                # Normalize the episode data to ensure consistent field access
                if "episodeNumber" not in ep and "number" in ep:
                    ep["episodeNumber"] = ep["number"]
                elif "number" not in ep and "episodeNumber" in ep:
                    ep["number"] = ep["episodeNumber"]
                return ep
        return None

    def _generate_new_filename(self, path: Path, series_info: Dict, episode_info: Dict) -> Optional[str]:
        """Generate new filename based on series and episode info."""
        try:
            series_name = series_info.get("translations", {}).get("deu") or series_info["name"]
            season_num = episode_info["seasonNumber"]
            
            # Try both possible field names for episode number
            episode_num = episode_info.get("number") or episode_info.get("episodeNumber")
            if episode_num is None:
                logger.error(f"Missing episode number in episode info: {episode_info}")
                return None
                
            episode_name = episode_info.get("translations", {}).get("deu") or episode_info.get("name", "")

            new_name = f"{series_name} - S{season_num:02d}E{episode_num:02d}"
            if episode_name:
                new_name += f" - {episode_name}"
            
            return f"{new_name}{path.suffix}"
        except (KeyError, TypeError) as e:  
            logger.error(f"Error generating filename: {e}, Episode info: {episode_info}")
            return None

    def _confirm_rename(self) -> bool:
        """Get user confirmation for rename operation."""
        return input("Proceed with rename? (y/n): ").lower() == 'y'

    def _perform_rename(self, old_path: Path, new_name: str) -> bool:
        """Perform the actual file rename operation."""
        try:
            new_path = old_path.parent / new_name
            if not self.dry_run:
                old_path.rename(new_path)
            return True
        except Exception as e:
            print(f"Error renaming file: {e}")
            return False
