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

# چند تا ویدیوی اخیر کانال اصلی را برای تحلیل جزئیات بکشد
MAX_RECENT_VIDEOS = 15


def get_channel_id(handle):
    url = f"{BASE_URL}/channels"
    params = {"part": "id", "forHandle": handle, "key": API_KEY}
    r = requests.get(url, params=params).json()
    items = r.get("items", [])
    return items[0]["id"] if items else None


def get_channel_stats(channel_id):
    url = f"{BASE_URL}/channels"
    params = {"part": "snippet,statistics,contentDetails", "id": channel_id, "key": API_KEY}
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
        "uploads_playlist_id": item["contentDetails"]["relatedPlaylists"]["uploads"],
    }


def get_recent_video_ids(uploads_playlist_id, max_results=MAX_RECENT_VIDEOS):
    """آخرین ویدیوهای منتشرشده در پلی‌لیست uploads کانال را برمی‌گرداند."""
    url = f"{BASE_URL}/playlistItems"
    params = {
        "part": "contentDetails",
        "playlistId": uploads_playlist_id,
        "maxResults": min(max_results, 50),
        "key": API_KEY,
    }
    r = requests.get(url, params=params).json()
    items = r.get("items", [])
    return [item["contentDetails"]["videoId"] for item in items]


def get_video_details(video_ids):
    """عنوان، توضیحات، آمار و مدت زمان هر ویدیو را (تا ۵۰ تا در یک درخواست) برمی‌گرداند."""
    if not video_ids:
        return []
    url = f"{BASE_URL}/videos"
    params = {
        "part": "snippet,statistics,contentDetails",
        "id": ",".join(video_ids),
        "key": API_KEY,
    }
    r = requests.get(url, params=params).json()
    details = []
    for item in r.get("items", []):
        snippet = item["snippet"]
        stats = item.get("statistics", {})
        details.append({
            "video_id": item["id"],
            "title": snippet.get("title"),
            "description": snippet.get("description"),
            "published_at": snippet.get("publishedAt"),
            "duration": item.get("contentDetails", {}).get("duration"),
            "views": stats.get("viewCount"),
            "likes": stats.get("likeCount"),
            "comments": stats.get("commentCount"),
        })
    return details


def get_transcript(video_id):
    """
    زیرنویس/ترانسکریپت واقعی ویدیو را با youtube-transcript-api می‌کشد.
    این کتابخانه به OAuth نیاز ندارد، اما فقط برای ویدیوهایی که زیرنویس
    (خودکار یا دستی) دارند کار می‌کند.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id, languages=["fa", "ps", "en"])
        return " ".join(chunk["text"] for chunk in transcript_list)
    except Exception as e:
        return f"[transcript not available: {e}]"


def main():
    if not API_KEY:
        raise SystemExit("YOUTUBE_API_KEY not set")

    results = {"fetched_at": datetime.utcnow().isoformat(), "channels": {}, "videos": []}

    for key, handle in CHANNELS.items():
        channel_id = handle if handle.startswith("UC") else get_channel_id(handle)
        if not channel_id:
            print(f"Could not resolve channel id for {handle}")
            continue
        stats = get_channel_stats(channel_id)
        if stats:
            results["channels"][key] = stats
            print(f"{key}: {stats}")

            # فقط برای کانال اصلی، جزئیات و ترانسکریپت ویدیوهای اخیر را می‌کشد
            if key == "main":
                video_ids = get_recent_video_ids(stats["uploads_playlist_id"])
                video_details = get_video_details(video_ids)
                for v in video_details:
                    v["transcript"] = get_transcript(v["video_id"])
                    print(f"  fetched details for: {v['title'][:50]}")
                results["videos"] = video_details

    os.makedirs("docs", exist_ok=True)
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("Saved to docs/data.json")


if __name__ == "__main__":
    main()
