"""Configuration management module."""
import json
import os
import logging
from typing import Dict, List, Optional, Callable

logger = logging.getLogger(__name__)

class Config:
    def __init__(self, config_dir: str = "~/.config/showrenamer"):
        self.config_dir = os.path.expanduser(config_dir)
        self.config_files = {
            'cache': 'show_cache.json',
            'patterns': 'name_patterns.json',
            'mapping': 'series_mapping.json',
            'directories': 'show_directories.json'
        }
        self._ensure_config_dir()
        self._load_configs()
        self._config_change_callbacks = {}

    def _ensure_config_dir(self):
        """Ensure configuration directory exists."""
        os.makedirs(self.config_dir, exist_ok=True)

    def _load_configs(self):
        """Load all configuration files."""
        self.patterns = self._load_file('patterns', self._default_patterns())
        self.mapping = self._load_file('mapping', self._default_mapping())
        self.directories = self._load_file('directories', self._default_directories())
        
    def reload_config(self, config_type: str):
        """
        Reload a specific configuration file.
        
        Args:
            config_type: Type of configuration to reload ('patterns', 'mapping', or 'directories')
        """
        logger.info(f"Reloading configuration: {config_type}")
        if config_type == 'patterns':
            self.patterns = self._load_file('patterns', self._default_patterns())
            self._notify_config_change(config_type)
        elif config_type == 'mapping':
            self.mapping = self._load_file('mapping', self._default_mapping())
            self._notify_config_change(config_type)
        elif config_type == 'directories':
            self.directories = self._load_file('directories', self._default_directories())
            self._notify_config_change(config_type)
        else:
            logger.warning(f"Unknown configuration type: {config_type}")
    
    def register_config_change_callback(self, config_type: str, callback: Callable[[Dict], None]):
        """
        Register a callback function to be called when a specific configuration changes.
        
        Args:
            config_type: Type of configuration to watch ('patterns', 'mapping', or 'directories')
            callback: Function to call when the configuration changes
        """
        if config_type not in self._config_change_callbacks:
            self._config_change_callbacks[config_type] = []
        self._config_change_callbacks[config_type].append(callback)
        
    def _notify_config_change(self, config_type: str):
        """
        Notify registered callbacks about a configuration change.
        
        Args:
            config_type: Type of configuration that changed
        """
        if config_type not in self._config_change_callbacks:
            return
            
        config_data = None
        if config_type == 'patterns':
            config_data = self.patterns
        elif config_type == 'mapping':
            config_data = self.mapping
        elif config_type == 'directories':
            config_data = self.directories
            
        if config_data:
            for callback in self._config_change_callbacks[config_type]:
                try:
                    callback(config_data)
                except Exception as e:
                    logger.error(f"Error in config change callback: {e}")

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

    def save_directories(self, directories: Dict):
        """Save show directories configuration."""
        self.directories = directories
        self._save_file('directories', directories)

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
                r"^(.*?)\s*-\s*s(\d{1,2})e(\d{1,2})(?:\s|$|\.|\[)",
                r"[._-]s(\d{1,2})e(\d{1,2})"
            ]
        }

    def _default_mapping(self) -> Dict:
        return {
            "dexteros": "Dexter: Original Sin",
            "ncis": "Navy CIS"
        }

    def _default_directories(self) -> Dict:
        return {
            "show_directories": [
                "/media/shows"  # Default show directory for Docker setup
            ]
        }
