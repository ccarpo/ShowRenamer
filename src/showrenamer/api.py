"""TVDB API client module."""
import requests
from typing import Dict, Optional

class TVDBClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api4.thetvdb.com/v4"
        self.bearer_token = None

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
        response = self._make_request("search", params={
            "query": query,
            "type": "series"
        })
        return response["data"] if response["data"] else None

    def get_episode_info(self, series_id: int) -> Dict:
        # Extract numeric ID if it's in the format 'series-12345'
        if isinstance(series_id, str) and series_id.startswith('series-'):
            numeric_id = series_id.split('-')[1]
        else:
            numeric_id = str(series_id)
            
        all_episodes = []
        page = 0
        while True:
            response = self._make_request(f"series/{numeric_id}/episodes/default/deu?page={page}")
            all_episodes.extend(response["data"]["episodes"])
            
            # Check if there are more pages
            links = response.get("links", {})
            if not links.get("next"):
                break
            page += 1
            
        return all_episodes
