"""Configuration management module."""
import json
import os
from typing import Dict

class Config:
    def __init__(self, config_dir: str = "~/.config/showrenamer"):
        self.config_dir = os.path.expanduser(config_dir)
        self.config_files = {
            'cache': 'show_cache.json',
            'patterns': 'name_patterns.json',
            'mapping': 'series_mapping.json',
        }
        self._ensure_config_dir()
        self._load_configs()

    def _ensure_config_dir(self):
        """Ensure configuration directory exists."""
        os.makedirs(self.config_dir, exist_ok=True)

    def _load_configs(self):
        """Load all configuration files."""
        self.patterns = self._load_file('patterns', self._default_patterns())
        self.mapping = self._load_file('mapping', self._default_mapping())

    def _load_file(self, config_type: str, default_data: Dict) -> Dict:
        """Load a specific configuration file."""
        file_path = os.path.join(self.config_dir, self.config_files[config_type])
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            self._save_file(config_type, default_data)
            return default_data

    def _save_file(self, config_type: str, data: Dict):
        """Save data to a configuration file."""
        file_path = os.path.join(self.config_dir, self.config_files[config_type])
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def save_mapping(self, mapping: Dict):
        """Save series mapping."""
        self.mapping = mapping
        self._save_file('mapping', mapping)

    def save_patterns(self, patterns: Dict):
        """Save name patterns."""
        self.patterns = patterns
        self._save_file('patterns', patterns)

    def _default_patterns(self) -> Dict:
        return {
            "prefixes": [
                r"^\d{1,4}[a-z]{1,3}[-.]",
                r"^(?:tt|tv|show)[-.]"
            ],
            "suffixes": [
                r"[-.](?:sd|hd|720p|1080p|x264|aac|dtshd|bluray)",
                r"[-.](?:web|webrip|hdtv|proper|internal)"
            ],
            "replacements": {
                "dots_to_spaces": True,
                "underscores_to_spaces": True,
                "dashes_to_spaces": True
            },
            "patterns": [
                r"^(.*?)\s*-\s*s(\d{1,2})e(\d{1,2})\s*-",
                r"[._-]s(\d{1,2})e(\d{1,2})"
            ]
        }

    def _default_mapping(self) -> Dict:
        return {
            "dexteros": "Dexter: Original Sin",
            "ncis": "Navy CIS"
        }
