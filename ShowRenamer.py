import os
import re
import json
import requests
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from fuzzywuzzy import fuzz
import argparse
import sys
from datetime import datetime, timedelta

class ShowRenamer:
    def __init__(self, api_key: str, cache_file: str = "show_cache.json", 
                 prefix_file: str = "name_patterns.json",
                 mapping_file: str = "series_mapping.json",
                 interactive: bool = True, preview: bool = True,
                 cache_ttl_days: int = 7):
        self.api_key = api_key
        self.cache_file = cache_file
        self.prefix_file = prefix_file
        self.mapping_file = mapping_file
        self.interactive = interactive
        self.preview = preview
        self.cache_ttl_days = cache_ttl_days
        self.base_url = "https://api4.thetvdb.com/v4"
        self.bearer_token = None
        self.cache = self._load_cache()
        self.name_patterns = self._load_name_patterns()
        self.series_mapping = self._load_series_mapping()
        # Liste gängiger Video-Dateierweiterungen
        self.video_extensions = {
            '.mkv', '.avi', '.mp4', '.m4v', '.mov',
            '.wmv', '.flv', '.mpg', '.mpeg', '.m2ts'
        }

    def _load_series_mapping(self) -> Dict[str, str]:
        """Lädt das Serien-Mapping aus der JSON-Datei"""
        default_mapping = {
            "dexteros": "Dexter: Original Sin",
            "ncis": "Navy CIS"
        }

        if os.path.exists(self.mapping_file):
            with open(self.mapping_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # Erstelle Datei mit Standardwerten
            with open(self.mapping_file, 'w', encoding='utf-8') as f:
                json.dump(default_mapping, f, ensure_ascii=False, indent=2)
            return default_mapping


    def _load_cache(self) -> Dict:
        if os.path.exists(self.cache_file):
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_cache(self):
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)

    def _get_bearer_token(self) -> str:
        if self.bearer_token:
            return self.bearer_token

        response = requests.post(
            f"{self.base_url}/login",
            json={"apikey": self.api_key}
        )
        response.raise_for_status()
        self.bearer_token = response.json()["data"]["token"]
        return self.bearer_token

    def _make_request(self, endpoint: str, method: str = "GET", **kwargs) -> Dict:
        headers = {"Authorization": f"Bearer {self._get_bearer_token()}"}
        response = requests.request(
            method,
            f"{self.base_url}/{endpoint}",
            headers=headers,
            **kwargs
        )
        response.raise_for_status()
        return response.json()

    def search_series(self, query: str) -> Optional[Dict]:
        # Zuerst im Cache nachsehen
        if query in self.cache:
            return self.cache[query]

        # API-Abfrage durchführen
        response = self._make_request("search", params={
            "query": query,
            "type": "series"
        })

        if not response["data"]:
            return None

        # Beste Übereinstimmung mit Fuzzy Matching finden
        best_match = None
        highest_ratio = 0

        for show in response["data"]:
            # Check original title
            ratio_original = fuzz.ratio(query.lower(), show["name"].lower())
            # Check German translation
            german_title = show.get("translations", {}).get("deu")
            ratio_german = fuzz.ratio(query.lower(), german_title.lower()) if german_title else 0
            # Determine highest ratio
            if ratio_original > highest_ratio or ratio_german > highest_ratio:
                highest_ratio = max(ratio_original, ratio_german)
                best_match = show

        if highest_ratio < 60:  # Schwellenwert für Übereinstimmung
            return None

        if self.interactive:
            confirm = input(f'Gefundene Serie: {best_match["name"]} ({best_match["year"]}). '
                          f'Ist das korrekt? (j/n): ').lower()
            if confirm != 'j':
                return None

        # Im Cache speichern
        self.cache[query] = best_match
        self._save_cache()
        return best_match

    def get_episode_info(self, series_id: int, force_refresh: bool = False) -> Dict:
        """Holt Episodeninformationen, aktualisiert Cache bei Bedarf"""
        cache_key = f"episodes_{series_id}"
        
        # Wenn force_refresh True ist oder die Episode nicht gefunden wurde,
        # hole neue Daten von der API
        if force_refresh or cache_key not in self.cache:
            response = self._make_request(f"series/{series_id}/episodes/default/deu")
            self.cache[cache_key] = response["data"]
            self._save_cache()
        
        return self.cache[cache_key]

    def parse_filename(self, filename: str) -> Optional[Tuple[str, int, int]]:
        """
        Extrahiert Serienname, Staffel und Episode aus dem Dateinamen
        """
        # Entferne Dateiendung
        base_name = os.path.splitext(filename)[0].lower()
        
        # Versuche alle konfigurierten Patterns
        for pattern in self.name_patterns.get("patterns", []):
            match = re.search(pattern, base_name)
            if match:
                # Das erste Pattern hat den Seriennamen in Gruppe 1
                if len(match.groups()) == 3:
                    show_part = match.group(1)
                    season = int(match.group(2))
                    episode = int(match.group(3))
                # Das zweite Pattern hat nur Staffel und Episode
                else:
                    show_part = base_name[:match.start()]
                    season = int(match.group(1))
                    episode = int(match.group(2))
                
                # Cleaning des Seriennamens nur wenn nötig
                possible_names = self._extract_possible_names(show_part)
                
                # Suche nach der besten Übereinstimmung
                for name in possible_names:
                    if self.search_series(name):
                        return name, season, episode
                
                # Wenn keine Übereinstimmung gefunden wurde, verwende den ersten Namen
                return possible_names[0] if possible_names else None, season, episode
                
        return None

    def _load_name_patterns(self) -> Dict:
        """Lädt die Namens-Muster aus der JSON-Datei"""
        default_patterns = {
            "prefixes": [
                r"^\d{1,4}[a-z]{1,3}[-.]",  # z.B. "4sf-"
                r"^(?:tt|tv|show)[-.]"       # z.B. "tt-" oder "tv-"
            ],
            "suffixes": [
                r"[-.](?:sd|hd|720p|1080p|x264|aac|dtshd|bluray)",
                r"[-.](?:web|webrip|hdtv|proper|internal)"
            ],
            "replacements": {
                "dots_to_spaces": True,      # Punkte zu Leerzeichen
                "underscores_to_spaces": True, # Unterstriche zu Leerzeichen
                "dashes_to_spaces": True     # Bindestriche zu Leerzeichen
            },
            "patterns": [
                r"^(.*?)\s*-\s*s(\d{1,2})e(\d{1,2})\s*-",
                r"[._-]s(\d{1,2})e(\d{1,2})"
            ]
        }

        if os.path.exists(self.prefix_file):
            with open(self.prefix_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # Erstelle Datei mit Standardwerten
            with open(self.prefix_file, 'w', encoding='utf-8') as f:
                json.dump(default_patterns, f, ensure_ascii=False, indent=2)
            return default_patterns

    def _extract_possible_names(self, show_part: str) -> List[str]:
        """Extrahiert mögliche Seriennamen basierend auf konfigurierten Mustern"""
        names = set()
        
        # Entferne konfigurierte Präfixe
        for prefix in self.name_patterns["prefixes"]:
            show_part = re.sub(prefix, '', show_part)
        
        # Entferne konfigurierte Suffixe
        for suffix in self.name_patterns["suffixes"]:
            show_part = re.sub(suffix + '.*$', '', show_part)
        
        # Prüfe das Mapping für den bereinigten Namen
        # cleaned_name = show_part.strip('.-_').lower()
        if show_part in self.series_mapping:
            names.add(self.series_mapping[show_part])
        else:
            # Wende konfigurierte Ersetzungen an
            replacements = self.name_patterns["replacements"]
            if replacements.get("dots_to_spaces"):
                names.add(show_part.replace('.', ' ').strip())
            
            if replacements.get("underscores_to_spaces"):
                names.add(show_part.replace('_', ' ').strip())
                
            if replacements.get("dashes_to_spaces"):
                names.add(show_part.replace('-', ' ').strip())
                    # Originaler bereinigter Name
            names.add(show_part.strip('.-_'))
            
        # Entferne leere Strings und normalisiere Whitespace
        return [' '.join(name.split()) for name in names if name]

    def generate_new_filename(self, show_name: str, season: int, 
                            episode: int, episode_name: str) -> str:
        invalid_chars = r'[<>:"/\\|?*]'
        safe_show_name = re.sub(invalid_chars, '-', show_name)
        safe_episode_name = re.sub(invalid_chars, '-', episode_name)
        return f"{safe_show_name} - S{season:02d}E{episode:02d} - {safe_episode_name}.mkv"

    def preview_rename(self, directory: str = "/media/truecrypt4/tmp/extracted") -> List[Tuple[str, str]]:
        """Zeigt eine Vorschau der Umbenennungen"""
        changes = []
        for filename in os.listdir(directory):
            if not any(filename.lower().endswith(ext) for ext in self.video_extensions):
                continue

            parsed = self.parse_filename(filename)
            if not parsed:
                continue

            show_prefix, season, episode = parsed
            series_info = self.search_series(show_prefix)
            
            if not series_info:
                print(f"Keine Serie gefunden für: {filename}")
                continue

            # Erste Anfrage ohne force_refresh
            episode_info = self.get_episode_info(series_info["tvdb_id"])
            
            # Suche nach der Episode
            episode_name = None
            for ep in episode_info["episodes"]:
                if ep["seasonNumber"] == season and ep["number"] == episode:
                    episode_name = ep["name"]
                    break

            # Wenn Episode nicht gefunden, aktualisiere Cache und versuche erneut
            if not episode_name:
                print(f"Episode nicht im Cache gefunden, aktualisiere Daten für: {filename}")
                episode_info = self.get_episode_info(series_info["tvdb_id"], force_refresh=True)
                
                # Zweiter Versuch nach Cache-Aktualisierung
                for ep in episode_info["episodes"]:
                    if ep["seasonNumber"] == season and ep["number"] == episode:
                        episode_name = ep["name"]
                        break

            if not episode_name:
                print(f"Keine Episodeninformation gefunden für: {filename}")
                continue

            series_name = series_info.get("translations", {}).get("deu", series_info["name"])
            new_name = self.generate_new_filename(series_name, season, episode, episode_name)
            changes.append((
                os.path.join(directory, filename),
                os.path.join(directory, new_name)
            ))

        return changes

    def rename_files(self, directory: str = "D:\\Code\\Private\\ShowRenamer", 
                    backup_file: str = "rename_backup.json") -> None:
        """Führt die Umbenennungen durch und erstellt ein Backup"""
        if self.preview:
            changes = self.preview_rename(directory)
            print("\nGeplante Änderungen:")
            for old, new in changes:
                print(f"{os.path.basename(old)} -> {os.path.basename(new)}")
            
            if self.interactive:
                confirm = input("\nMöchten Sie diese Änderungen durchführen? (j/n): ").lower()
                if confirm != 'j':
                    print("Abgebrochen.")
                    return

        # Backup erstellen
        backup = {}
        for old_path, new_path in changes:
            try:
                os.rename(old_path, new_path)
                backup[new_path] = old_path
            except OSError as e:
                print(f"Fehler beim Umbenennen von {old_path}: {e}")

        # Backup speichern
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(backup, f, ensure_ascii=False, indent=2)

    def undo_rename(self, backup_file: str = "rename_backup.json") -> None:
        """Macht die letzten Umbenennungen rückgängig"""
        if not os.path.exists(backup_file):
            print("Keine Backup-Datei gefunden.")
            return

        with open(backup_file, 'r', encoding='utf-8') as f:
            backup = json.load(f)

        if self.interactive:
            print("\nFolgende Änderungen werden rückgängig gemacht:")
            for new, old in backup.items():
                print(f"{os.path.basename(new)} -> {os.path.basename(old)}")
            
            confirm = input("\nMöchten Sie fortfahren? (j/n): ").lower()
            if confirm != 'j':
                print("Abgebrochen.")
                return

        for new_path, old_path in backup.items():
            try:
                if os.path.exists(new_path):
                    os.rename(new_path, old_path)
                else:
                    print(f"Warnung: Datei {new_path} existiert nicht mehr.")
            except OSError as e:
                print(f"Fehler beim Wiederherstellen von {new_path}: {e}")

        # Backup-Datei löschen
        os.remove(backup_file)

    def update_patterns(self, new_patterns: Dict) -> None:
        """Aktualisiert die Namens-Muster"""
        self.name_patterns.update(new_patterns)
        with open(self.prefix_file, 'w', encoding='utf-8') as f:
            json.dump(self.name_patterns, f, ensure_ascii=False, indent=2)

    @staticmethod
    def load_api_key(key_file: str = ".env") -> Optional[str]:
        """Lädt den API-Key aus einer .env Datei oder Umgebungsvariable"""
        # Prüfe zuerst Umgebungsvariable
        api_key = os.getenv('TVDB_API_KEY')
        if api_key:
            return api_key

        # Dann .env Datei
        if os.path.exists(key_file):
            with open(key_file, 'r') as f:
                for line in f:
                    if line.startswith('TVDB_API_KEY='):
                        return line.split('=')[1].strip()
        
        return None

def main():
    parser = argparse.ArgumentParser(description='Rename TV show files using TVDB API')
    
    # Haupt-Aktionsgruppe
    action_group = parser.add_mutually_exclusive_group()
    action_group.add_argument('--rename', action='store_true', default=True,
                          help='Führe Umbenennung durch (Standard)')
    action_group.add_argument('--undo', action='store_true',
                          help='Mache letzte Umbenennung rückgängig')
    
    # Weitere Optionen
    parser.add_argument('--api-key', help='TVDB API key')
    parser.add_argument('--key-file', default='.env', help='File containing TVDB API key')
    parser.add_argument('--no-interactive', action='store_true', 
                       help='Disable interactive mode')
    parser.add_argument('--no-preview', action='store_true', 
                       help='Disable preview mode')
    parser.add_argument('--directory', default='D:\\Code\\Private\\ShowRenamer', 
                       help='Directory containing video files')
    parser.add_argument('--backup-file', default='rename_backup.json',
                       help='Backup file for undo operation')
    
    args = parser.parse_args()

    # API Key Priorität:
    # 1. Kommandozeilen-Argument
    # 2. Umgebungsvariable oder .env Datei
    api_key = args.api_key or ShowRenamer.load_api_key(args.key_file)
    
    if not api_key:
        print("Fehler: Kein API-Key gefunden. Bitte über --api-key übergeben oder in .env Datei speichern.")
        sys.exit(1)

    renamer = ShowRenamer(
        api_key=api_key,
        interactive=not args.no_interactive,
        preview=not args.no_preview
    )

    try:
        if args.undo:
            renamer.undo_rename(args.backup_file)
        else:
            renamer.rename_files(args.directory, args.backup_file)
    except Exception as e:
        print(f"Ein Fehler ist aufgetreten: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
