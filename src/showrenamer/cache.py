"""Cache management module."""
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

class Cache:
    def __init__(self, cache_file: str, ttl_days: int = 7):
        self.cache_file = cache_file
        self.ttl_days = ttl_days
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict:
        """Load cache from file."""
        if os.path.exists(self.cache_file):
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
                self._clean_expired_entries(cache_data)
                return cache_data
        return {}

    def _clean_expired_entries(self, cache_data: Dict):
        """Remove expired cache entries."""
        now = datetime.now()
        expired_keys = []
        
        for key, value in cache_data.items():
            if isinstance(value, dict) and 'timestamp' in value:
                timestamp = datetime.fromisoformat(value['timestamp'])
                if now - timestamp > timedelta(days=self.ttl_days):
                    expired_keys.append(key)
        
        for key in expired_keys:
            del cache_data[key]

    def save(self):
        """Save cache to file."""
        with open(self.cache_file, 'w', encoding='utf-8') as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)

    def get(self, key: str) -> Optional[Dict]:
        """Get value from cache if not expired."""
        if key in self.cache:
            value = self.cache[key]
            if isinstance(value, dict) and 'timestamp' in value:
                timestamp = datetime.fromisoformat(value['timestamp'])
                if datetime.now() - timestamp <= timedelta(days=self.ttl_days):
                    return value['data']
                # Entry is expired, return None to trigger refresh
                return None
            # Old format without timestamp, return as-is for backward compatibility
            return value
        return None

    def set(self, key: str, value: Any, with_timestamp: bool = True):
        """Set value in cache with optional timestamp."""
        if with_timestamp:
            self.cache[key] = {
                'data': value,
                'timestamp': datetime.now().isoformat()
            }
        else:
            self.cache[key] = value
        self.save()

    def clear(self):
        """Clear all cache entries."""
        self.cache = {}
        self.save()
