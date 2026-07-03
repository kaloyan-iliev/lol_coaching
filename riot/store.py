"""
Disk storage for Riot API data: raw match/timeline JSON, the baseline match
index, and resumable discovery state.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config


def ensure_dirs():
    for d in (config.MATCHES_DIR, config.TIMELINES_DIR, config.FACTS_DIR, config.REVIEWS_DIR):
        os.makedirs(d, exist_ok=True)


def _read_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


# --- raw match / timeline JSON ---

def match_path(match_id: str) -> str:
    return os.path.join(config.MATCHES_DIR, f"{match_id}.json")


def timeline_path(match_id: str) -> str:
    return os.path.join(config.TIMELINES_DIR, f"{match_id}.json")


def save_match(match_id: str, data: dict):
    _write_json(match_path(match_id), data)


def save_timeline(match_id: str, data: dict):
    _write_json(timeline_path(match_id), data)


def load_match(match_id: str) -> dict | None:
    return _read_json(match_path(match_id), None)


def load_timeline(match_id: str) -> dict | None:
    return _read_json(timeline_path(match_id), None)


# --- match index ---

def load_index() -> list[dict]:
    return _read_json(config.MATCH_INDEX_FILE, [])


def save_index(index: list[dict]):
    os.makedirs(config.RIOT_DIR, exist_ok=True)
    with open(config.MATCH_INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


def add_index_entry(entry: dict):
    index = load_index()
    if any(e["match_id"] == entry["match_id"] for e in index):
        return
    index.append(entry)
    save_index(index)


# --- discovery state (resumable across dev-key expiry) ---

def load_discovery_state() -> dict:
    return _read_json(config.DISCOVERY_STATE_FILE, {
        "scanned_puuids": [],
        "checked_match_ids": [],
    })


def save_discovery_state(state: dict):
    _write_json(config.DISCOVERY_STATE_FILE, state)
