import os
import json
import requests
from datetime import datetime

API_KEY = os.environ.get("YOUTUBE_API_KEY")
BASE_URL = "https://www.googleapis.com/youtube/v3"

CHANNELS = {
    "main": "tanzcartoon",
    "competitor_1": "arabichouseremix",
    "competitor_2": "ai-bebino",
    "competitor_3_id": "UC_woxD5GYiaCfxHyjiuUAHg",
    "competitor_4": "enam455",
    "competitor_5": "melodyhouse001",
}

def get_channel_id(handle):
    url = f"{BASE_URL}/channels"
    params = {"part": "id", "forHandle": handle, "key": API_KEY}
    r = requests.get(url, params=params).json()
    items = r.get("items", [])
    return items[0]["id"] if items else None

def get_channel_stats(channel_id):
    url = f"{BASE_URL}/channels"
    params = {"part": "snippet,statistics", "id": channel_id, "key": API_KEY}
    r = requests.get(url, params=params).json()
    items = r.get("items", [])
    if not items:
        return None
    item = items[0]
    return {
        "title": item["snippet"]["title"],
        "subscribers": item["statistics"].get("subscriberCount"),
        "views": item["statistics"].get("viewCount"),
        "videos": item["statistics"].get("videoCount"),
    }

def main():
    if not API_KEY:
        raise SystemExit("YOUTUBE_API_KEY not set")

    results = {"fetched_at": datetime.utcnow().isoformat(), "channels": {}}

    for key, handle in CHANNELS.items():
        channel_id = handle if handle.startswith("UC") else get_channel_id(handle)
        if not channel_id:
            print(f"Could not resolve channel id for {handle}")
            continue
        stats = get_channel_stats(channel_id)
        if stats:
            results["channels"][key] = stats
            print(f"{key}: {stats}")

    os.makedirs("docs", exist_ok=True)
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("Saved to dashboard/data.json")

if __name__ == "__main__":
    main()
