import os
import re
import json
import requests
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from fuzzywuzzy import fuzz
import argparse
import sys

class ShowRenamer:
    def __init__(self, api_key: str, cache_file: str = "show_cache.json", 
                 interactive: bool = True, preview: bool = True):
        self.api_key = api_key
        self.cache_file = cache_file
        self.interactive = interactive
        self.preview = preview
        self.base_url = "https://api4.thetvdb.com/v4"
        self.bearer_token = None
        self.cache = self._load_cache()
        # Liste gängiger Video-Dateierweiterungen
        self.video_extensions = {
            '.mkv', '.avi', '.mp4', '.m4v', '.mov',
            '.wmv', '.flv', '.mpg', '.mpeg', '.m2ts'
        }

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
            ratio = fuzz.ratio(query.lower(), show["name"].lower())
            if ratio > highest_ratio:
                highest_ratio = ratio
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

    def get_episode_info(self, series_id: int) -> Dict:
        response = self._make_request(f"series/{series_id}/episodes/default/deu")
        return response["data"]

    def parse_filename(self, filename: str) -> Optional[Tuple[str, int, int]]:
        """
        Extrahiert Serienname, Staffel und Episode aus dem Dateinamen
        Unterstützt verschiedene Namensformate:
        - 4sf-silo.sd.s01e01.mkv
        - show.name.s01e01.mkv
        - show_name_s01e01.mkv
        """
        # Entferne Dateiendung
        base_name = os.path.splitext(filename)[0].lower()
        
        # Suche nach Staffel und Episode
        pattern = r'[._-]s(\d{1,2})e(\d{1,2})'
        season_ep_match = re.search(pattern, base_name)
        
        if not season_ep_match:
            return None
            
        season = int(season_ep_match.group(1))
        episode = int(season_ep_match.group(2))
        
        # Extrahiere den Teil vor s01e01
        show_part = base_name[:season_ep_match.start()]
        
        # Verschiedene Cleaning-Strategien für den Seriennamen
        possible_names = self._extract_possible_names(show_part)
        
        # Suche nach der besten Übereinstimmung
        for name in possible_names:
            if self.search_series(name):
                return name, season, episode
                
        # Wenn keine Übereinstimmung gefunden wurde, verwende den ersten Namen
        return possible_names[0] if possible_names else None, season, episode

    def _extract_possible_names(self, show_part: str) -> List[str]:
        """
        Extrahiert mögliche Seriennamen aus dem Dateinamenteil
        """
        names = set()
        
        # Entferne bekannte Präfixe/Suffixe
        show_part = re.sub(r'^(?:\d{1,4}[a-z]{1,3}[-.])', '', show_part)  # z.B. "4sf-"
        show_part = re.sub(r'(?:[-.](?:sd|hd|720p|1080p|x264|aac|dtshd|bluray))+.*$', '', show_part)
        
        # Originaler bereinigter Name
        names.add(show_part.strip('.-_'))
        
        # Punkte durch Leerzeichen ersetzen
        dot_to_space = show_part.replace('.', ' ').strip()
        names.add(dot_to_space)
        
        # Unterstriche durch Leerzeichen ersetzen
        underscore_to_space = show_part.replace('_', ' ').strip()
        names.add(underscore_to_space)
        
        # Bindestriche durch Leerzeichen ersetzen
        dash_to_space = show_part.replace('-', ' ').strip()
        names.add(dash_to_space)
        
        # Alle Trennzeichen durch Leerzeichen ersetzen
        all_to_space = re.sub(r'[._-]', ' ', show_part).strip()
        names.add(all_to_space)
        
        # Entferne leere Strings und normalisiere Whitespace
        return [' '.join(name.split()) for name in names if name]

    def generate_new_filename(self, show_name: str, season: int, 
                            episode: int, episode_name: str) -> str:
        return f"{show_name} - S{season:02d}E{episode:02d} - {episode_name}.mkv"

    def preview_rename(self, directory: str = "/media/truecrypt4/tmp/extraced") -> List[Tuple[str, str]]:
        """Zeigt eine Vorschau der Umbenennungen"""
        changes = []
        for filename in os.listdir(directory):
            # Prüfe auf gültige Videoendung
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

            episode_info = self.get_episode_info(series_info["tvdb_id"])
            
            # Finde die richtige Episode
            episode_name = None
            for ep in episode_info["episodes"]:
                if ep["seasonNumber"] == season and ep["number"] == episode:
                    episode_name = ep["name"]
                    break

            if not episode_name:
                print(f"Keine Episodeninformation gefunden für: {filename}")
                continue

            # Hole den deutschen Namen aus den Übersetzungen, falls vorhanden
            series_name = series_info.get("translations", {}).get("deu", series_info["name"])

            new_name = self.generate_new_filename(series_name, season, episode, episode_name)
            changes.append((
                os.path.join(directory, filename),
                os.path.join(directory, new_name)
            ))

        return changes

    def rename_files(self, directory: str = "/media/truecrypt4/tmp/extraced", 
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
    parser.add_argument('--api-key', help='TVDB API key')
    parser.add_argument('--key-file', default='.env', help='File containing TVDB API key')
    parser.add_argument('--no-interactive', action='store_true', help='Disable interactive mode')
    parser.add_argument('--no-preview', action='store_true', help='Disable preview mode')
    parser.add_argument('--directory', default='/media/truecrypt4/tmp/extraced', 
                       help='Directory containing video files')
    
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
        renamer.rename_files(args.directory)
    except Exception as e:
        print(f"Ein Fehler ist aufgetreten: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
