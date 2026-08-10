import os
import json
import requests
from datetime import datetime

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CHANNEL_HANDLE = "tanzcartoon"

YOUTUBE_BASE = "https://www.googleapis.com/youtube/v3"


def get_channel_id(handle):
    url = f"{YOUTUBE_BASE}/channels"
    params = {"part": "id,contentDetails", "forHandle": handle, "key": YOUTUBE_API_KEY}
    r = requests.get(url, params=params).json()
    items = r.get("items", [])
    if not items:
        return None, None
    return items[0]["id"], items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def get_recent_videos(uploads_playlist_id, max_results=8):
    url = f"{YOUTUBE_BASE}/playlistItems"
    params = {
        "part": "snippet",
        "playlistId": uploads_playlist_id,
        "maxResults": max_results,
        "key": YOUTUBE_API_KEY,
    }
    r = requests.get(url, params=params).json()
    videos = []
    for item in r.get("items", []):
        sn = item["snippet"]
        videos.append({
            "title": sn.get("title", ""),
            "description": (sn.get("description", "") or "")[:300],
            "video_id": sn["resourceId"]["videoId"],
        })
    return videos


def get_video_stats(video_ids):
    if not video_ids:
        return {}
    url = f"{YOUTUBE_BASE}/videos"
    params = {"part": "statistics", "id": ",".join(video_ids), "key": YOUTUBE_API_KEY}
    r = requests.get(url, params=params).json()
    stats = {}
    for item in r.get("items", []):
        stats[item["id"]] = item.get("statistics", {})
    return stats


def build_prompt(videos):
    lines = ["اینها آخرین ویدیوهای کانال طنز خانوادگی «طنزکارتون» با کاراکترهای ثابت مادرکلان و نواسه هستند:\n"]
    for v in videos:
        views = v.get("views", "?")
        lines.append(f"- عنوان: {v['title']} | بازدید: {views} | توضیح: {v['description']}")

    lines.append("""
با توجه به این ویدیوها، یک سناریوی طنز جدید (کوتاه، برای فرمت شورت ۴۰-۶۰ ثانیه‌ای) با همان کاراکترهای مادرکلان و نواسه پیشنهاد بده که:
1. با موضوعات قبلی تکراری نباشد
2. یک هوک قوی در ۳ ثانیه‌ی اول داشته باشد
3. یک چرخش طنز (twist) در پایان داشته باشد

پاسخ را دقیقا به این فرمت JSON بده و هیچ متن اضافه‌ای ننویس:
{
  "title": "عنوان پیشنهادی",
  "hook": "جمله‌ی هوک ابتدایی",
  "scenario": "شرح کامل سناریو در ۳-۴ جمله",
  "twist": "توضیح چرخش پایانی"
}
""")
    return "\n".join(lines)


def call_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    r = requests.post(url, json=payload)
    r.raise_for_status()
    data = r.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


def main():
    if not YOUTUBE_API_KEY or not GEMINI_API_KEY:
        raise SystemExit("Missing YOUTUBE_API_KEY or GEMINI_API_KEY")

    channel_id, uploads_id = get_channel_id(CHANNEL_HANDLE)
    if not uploads_id:
        raise SystemExit("Could not resolve channel uploads playlist")

    videos = get_recent_videos(uploads_id)
    stats = get_video_stats([v["video_id"] for v in videos])
    for v in videos:
        v["views"] = stats.get(v["video_id"], {}).get("viewCount", "0")

    prompt = build_prompt(videos)
    suggestion = call_gemini(prompt)

    result = {
        "generated_at": datetime.utcnow().isoformat(),
        "based_on_videos": [v["title"] for v in videos],
        "suggestion": suggestion,
    }

    os.makedirs("docs", exist_ok=True)
    with open("docs/suggestion.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print("Suggestion saved:", suggestion.get("title"))


if __name__ == "__main__":
    main()
