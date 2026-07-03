"""
Rate-limited Riot API client.

Respects dev-key app limits (20 req/s, 100 req/2min) with headroom, honors
429 Retry-After, retries 5xx, and raises a clear error when the daily dev
key has expired.
"""

import os
import sys
import time
from collections import deque

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config


class RiotAPIError(Exception):
    pass


class DevKeyExpired(RiotAPIError):
    pass


class RiotClient:
    # Stay under 100 req/2min and 20 req/s app limits with headroom
    WINDOW_2MIN_CAP = 95
    WINDOW_1SEC_CAP = 15

    def __init__(self, api_key: str | None = None,
                 platform: str | None = None, region: str | None = None):
        self.api_key = api_key or config.RIOT_API_KEY
        if not self.api_key or self.api_key.startswith("your_"):
            raise DevKeyExpired(
                "No RIOT_API_KEY set. Get a dev key at https://developer.riotgames.com "
                "and put it in .env"
            )
        self.platform_host = f"https://{platform or config.RIOT_PLATFORM}.api.riotgames.com"
        self.region_host = f"https://{region or config.RIOT_REGION}.api.riotgames.com"
        self.session = requests.Session()
        self.session.headers["X-Riot-Token"] = self.api_key
        self._timestamps: deque[float] = deque()

    def _throttle(self):
        now = time.time()
        while self._timestamps and now - self._timestamps[0] > 120:
            self._timestamps.popleft()

        if len(self._timestamps) >= self.WINDOW_2MIN_CAP:
            wait = 120 - (now - self._timestamps[0]) + 0.1
            if wait > 0:
                print(f"    (2min window full, waiting {wait:.0f}s...)")
                time.sleep(wait)

        recent = [t for t in self._timestamps if time.time() - t < 1.0]
        if len(recent) >= self.WINDOW_1SEC_CAP:
            time.sleep(1.0 - (time.time() - recent[0]) + 0.05)

    def _get(self, host: str, path: str, params: dict | None = None, retries: int = 3):
        """GET with rate limiting. Returns parsed JSON, or None on 404."""
        url = host + path
        for attempt in range(retries + 1):
            self._throttle()
            try:
                resp = self.session.get(url, params=params, timeout=15)
            except requests.RequestException as e:
                if attempt == retries:
                    raise RiotAPIError(f"Network error for {url}: {e}")
                time.sleep(2 ** attempt)
                continue
            self._timestamps.append(time.time())

            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", "10"))
                print(f"    (429 rate limited, sleeping {wait}s...)")
                time.sleep(wait + 1)
                continue
            if resp.status_code in (401, 403):
                raise DevKeyExpired(
                    "Riot API key rejected (401/403). Dev keys expire after 24h - "
                    "regenerate at https://developer.riotgames.com, update .env, and rerun. "
                    "All fetch scripts resume where they left off."
                )
            if resp.status_code == 404:
                return None
            if resp.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            raise RiotAPIError(f"HTTP {resp.status_code} for {url}: {resp.text[:200]}")
        raise RiotAPIError(f"Giving up after {retries} retries: {url}")

    # --- league-v4 (platform host) ---

    def master_plus_entries(self, queue: str = "RANKED_SOLO_5x5",
                            tiers: tuple[str, ...] = ("CHALLENGER", "GRANDMASTER", "MASTER")) -> list[dict]:
        """Ladder entries for the given tiers, best first. Entries include puuid."""
        paths = {
            "CHALLENGER": "challengerleagues",
            "GRANDMASTER": "grandmasterleagues",
            "MASTER": "masterleagues",
        }
        entries = []
        for tier in tiers:
            data = self._get(self.platform_host, f"/lol/league/v4/{paths[tier]}/by-queue/{queue}")
            tier_entries = sorted(data.get("entries", []),
                                  key=lambda e: e.get("leaguePoints", 0), reverse=True)
            for e in tier_entries:
                e["tier"] = tier
                entries.append(e)
        return entries

    # --- champion-mastery-v4 (platform host) ---

    def top_mastery(self, puuid: str, count: int = 3) -> list[dict]:
        return self._get(
            self.platform_host,
            f"/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}/top",
            params={"count": count},
        ) or []

    # --- match-v5 (regional host) ---

    def match_ids(self, puuid: str, queue: int = 420, count: int = 30, start: int = 0) -> list[str]:
        return self._get(
            self.region_host,
            f"/lol/match/v5/matches/by-puuid/{puuid}/ids",
            params={"queue": queue, "count": count, "start": start},
        ) or []

    def match(self, match_id: str) -> dict | None:
        return self._get(self.region_host, f"/lol/match/v5/matches/{match_id}")

    def timeline(self, match_id: str) -> dict | None:
        return self._get(self.region_host, f"/lol/match/v5/matches/{match_id}/timeline")

    # --- account-v1 (regional host) ---

    def account_by_riot_id(self, game_name: str, tag_line: str) -> dict | None:
        return self._get(
            self.region_host,
            f"/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}",
        )
