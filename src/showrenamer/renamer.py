"""File renaming module."""
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from fuzzywuzzy import fuzz

class FileRenamer:
    def __init__(self, 
                 api_client,
                 cache,
                 config,
                 interactive: bool = True,
                 preview: bool = True):
        self.api_client = api_client
        self.cache = cache
        self.config = config
        self.interactive = interactive
        self.preview = preview
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

        if self.preview:
            print(f"Would rename: {path.name} -> {new_name}")
            if self.interactive:
                if not self._confirm_rename():
                    return False
        
        return self._perform_rename(path, new_name)

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
        name = name.strip()
        
        # Remove prefixes
        for prefix in self.config.patterns["prefixes"]:
            name = re.sub(prefix, "", name)
        
        # Remove suffixes
        for suffix in self.config.patterns["suffixes"]:
            name = re.sub(suffix, "", name, flags=re.IGNORECASE)
        
        # Apply replacements
        if self.config.patterns["replacements"]["dots_to_spaces"]:
            name = name.replace(".", " ")
        if self.config.patterns["replacements"]["underscores_to_spaces"]:
            name = name.replace("_", " ")
        if self.config.patterns["replacements"]["dashes_to_spaces"]:
            name = name.replace("-", " ")
        
        # Clean up extra spaces and apply mapping
        name = " ".join(name.split())
        return self.config.mapping.get(name, name)

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
        
        if not episodes:
            episodes = self.api_client.get_episode_info(series_id)
            self.cache.set(cache_key, episodes)

        for ep in episodes:
            if ep.get("seasonNumber") == season and ep.get("number") == episode:
                return ep
        return None

    def _generate_new_filename(self, path: Path, series_info: Dict, episode_info: Dict) -> Optional[str]:
        """Generate new filename based on series and episode info."""
        try:
            series_name = series_info.get("translations", {}).get("deu") or series_info["name"]
            season_num = episode_info["seasonNumber"]
            episode_num = episode_info["number"]
            episode_name = episode_info.get("translations", {}).get("deu") or episode_info.get("name", "")

            new_name = f"{series_name} - S{season_num:02d}E{episode_num:02d}"
            if episode_name:
                new_name += f" - {episode_name}"
            
            return f"{new_name}{path.suffix}"
        except (KeyError, TypeError):
            return None

    def _confirm_rename(self) -> bool:
        """Get user confirmation for rename operation."""
        return input("Proceed with rename? (y/n): ").lower() == 'y'

    def _perform_rename(self, old_path: Path, new_name: str) -> bool:
        """Perform the actual file rename operation."""
        try:
            new_path = old_path.parent / new_name
            if not self.preview:
                old_path.rename(new_path)
            return True
        except Exception as e:
            print(f"Error renaming file: {e}")
            return False
