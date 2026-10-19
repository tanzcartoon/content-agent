import os
import json
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CHANNEL_HANDLE = "tanzcartoon"

GEMINI_MODEL = "gemini-3.8-flash"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    + GEMINI_MODEL
    + ":generateContent"
)
YOUTUBE_BASE = "https://www.googleapis.com/youtube/v3"

MAX_HISTORY = 60

# شخصیت‌های ثابت کانال. فقط از همین‌ها استفاده می‌شود.
# اگر نام یا ویژگی‌ای باید عوض شود، همین‌جا ویرایش کن.
CHARACTERS = [
    "مادرکلان (حدود ۶۰ ساله، کمی عصبی و گلایه‌مند، با اعصاب خراب سؤال می‌کند)",
    "نواسه (سیرت ۲۵ ساله، آرام و ملایم، با آرامش جواب می‌دهد)",
    "خانم نواسه (نسترن، ۲۲ ساله)",
    "پدر نواسه (۴۲ ساله)",
    "مادر نواسه (۴۰ ساله)",
]

SCHEMA = """{
  "upload_time_kabul": "18:30",
  "upload_reason": "دلیل انتخاب این ساعت در یک جمله",
  "short": {
    "title": "عنوان شورت",
    "hook": "جمله‌ی هوک ۳ ثانیه‌ی اول",
    "scenario": "شرح سناریو در ۳ تا ۴ جمله، با ذکر نام شخصیت‌ها",
    "twist": "چرخش طنز پایانی",
    "thumbnail_text": "متن کوتاه روی تامبنیل (حداکثر ۴ کلمه)",
    "thumbnail_image": "توصیف تصویر تامبنیل در یک جمله",
    "hashtags": ["#هشتگ۱", "#shorts"]
  },
  "long": {
    "title": "عنوان ویدیوی طولانی",
    "hook": "جمله‌ی هوک",
    "scenario": "خلاصه‌ی داستان در ۳ تا ۴ جمله، با ذکر نام شخصیت‌ها",
    "beats": [
      "۱) هوک",
      "۲) کاشتن نشانه",
      "۳) رسوایی اصلی",
      "۴) واکنش فیزیکی",
      "۵) فرود و دعوت به اقدام"
    ],
    "thumbnail_text": "متن کوتاه روی تامبنیل (حداکثر ۴ کلمه)",
    "thumbnail_image": "توصیف تصویر تامبنیل در یک جمله",
    "hashtags": ["#هشتگ۱", "#هشتگ۲"]
  }
}"""


def get_zone(name, offset_hours):
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone(timedelta(hours=offset_hours))


KABUL = get_zone("Asia/Kabul", 4.5)
BERLIN = get_zone("Europe/Berlin", 1)


def get_channel_id(handle):
    url = YOUTUBE_BASE + "/channels"
    params = {"part": "id,contentDetails", "forHandle": handle, "key": YOUTUBE_API_KEY}
    r = requests.get(url, params=params).json()
    items = r.get("items", [])
    if not items:
        return None, None
    return items[0]["id"], items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def get_recent_videos(uploads_playlist_id, max_results=10):
    url = YOUTUBE_BASE + "/playlistItems"
    params = {
        "part": "snippet,contentDetails",
        "playlistId": uploads_playlist_id,
        "maxResults": max_results,
        "key": YOUTUBE_API_KEY,
    }
    r = requests.get(url, params=params).json()
    videos = []
    for item in r.get("items", []):
        sn = item["snippet"]
        cd = item.get("contentDetails", {})
        videos.append({
            "title": sn.get("title", ""),
            "video_id": cd.get("videoId") or sn["resourceId"]["videoId"],
            "published_at": cd.get("videoPublishedAt") or sn.get("publishedAt", ""),
        })
    return videos


def get_video_stats(video_ids):
    if not video_ids:
        return {}
    url = YOUTUBE_BASE + "/videos"
    params = {"part": "statistics", "id": ",".join(video_ids), "key": YOUTUBE_API_KEY}
    r = requests.get(url, params=params).json()
    stats = {}
    for item in r.get("items", []):
        stats[item["id"]] = item.get("statistics", {})
    return stats


def hour_kabul(iso_string):
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return dt.astimezone(KABUL).strftime("%H:%M")
    except Exception:
        return "?"


def format_upload_time(hhmm):
    try:
        hour, minute = [int(x) for x in str(hhmm).strip().split(":")[:2]]
        now_kabul = datetime.now(KABUL)
        target = now_kabul.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target <= now_kabul:
            target = target + timedelta(days=1)
        day = "امروز" if target.date() == now_kabul.date() else "فردا"
        target_berlin = target.astimezone(BERLIN)
        return "{} ساعت {} به وقت افغانستان | {} به وقت اروپا (آلمان)".format(
            day, target.strftime("%H:%M"), target_berlin.strftime("%H:%M")
        )
    except Exception:
        return ""


def load_previous():
    try:
        with open("docs/suggestion.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def entry_from(sug, when):
    short_item = sug.get("short")
    if not short_item and sug.get("title"):
        short_item = sug
    short_item = short_item or {}
    long_item = sug.get("long") or {}
    return {
        "date": when,
        "short_title": short_item.get("title", ""),
        "short_summary": str(short_item.get("scenario", ""))[:150],
        "long_title": long_item.get("title", ""),
        "long_summary": str(long_item.get("scenario", ""))[:150],
    }


def norm(text):
    return "".join(str(text).split()).lower()


def find_duplicates(sug, history, videos):
    used = set()
    for h in history:
        used.add(norm(h.get("short_title", "")))
        used.add(norm(h.get("long_title", "")))
    for v in videos:
        used.add(norm(v.get("title", "")))
    used.discard("")
    dups = []
    for key in ("short", "long"):
        title = (sug.get(key) or {}).get("title", "")
        if title and norm(title) in used:
            dups.append(title)
    return dups


def build_prompt(videos, history, extra_note=""):
    lines = []
    lines.append("تو دستیار تولید محتوای کانال یوتیوب طنز خانوادگی «طنزکارتون» هستی. مخاطب اصلی کانال مردم افغانستان‌اند.")
    lines.append("")
    lines.append("شخصیت‌های ثابت کانال (فقط از همین‌ها استفاده کن، هیچ شخصیت جدیدی اضافه نکن و نام یا نقش‌شان را عوض نکن):")
    for c in CHARACTERS:
        lines.append("- " + c)
    lines.append("")
    lines.append("آخرین ویدیوهای کانال (عنوان | بازدید | ساعت انتشار به وقت افغانستان):")
    for v in videos:
        lines.append("- {} | {} | {}".format(v["title"], v.get("views", "?"), v.get("hour_kabul", "?")))
    lines.append("")
    if history:
        lines.append("موضوع‌های قبلاً پیشنهادشده (هرگز تکرار نکن، نه همان موضوع و نه روایت مشابه با اسم یا مکان دیگر):")
        for h in history[-40:]:
            if h.get("short_title"):
                lines.append("- شورت: {} | {}".format(h.get("short_title"), h.get("short_summary", "")))
            if h.get("long_title"):
                lines.append("- طولانی: {} | {}".format(h.get("long_title"), h.get("long_summary", "")))
        lines.append("")
    lines.append("قواعد:")
    lines.append("1. همه‌ی متن‌ها به فارسی دری و لهجه‌ی افغانی باشد. از کلمات افغانی استفاده کن (پیسه به جای پول، وخت به جای وقت، گپ، حویلی، موتر، کلکین) و از کلمات ایرانی استفاده نکن.")
    lines.append("2. مادرکلان کمی عصبی گلایه می‌کند و نواسه با آرامش جواب می‌دهد.")
    lines.append("3. موضوع باید کاملاً تازه باشد و با ویدیوهای بالا و فهرست موضوع‌های قبلی تکراری یا شبیه نباشد.")
    lines.append("4. عنوان و تامبنیل باید دقیقاً با محتوای واقعی ویدیو هم‌خوان باشند. عنوان یا تامبنیل گمراه‌کننده بازدید را پایین می‌آورد.")
    lines.append("5. بهترین ساعت انتشار را از روی جدول بالا (ساعت انتشار در برابر بازدید) انتخاب کن، به وقت افغانستان و با قالب HH:MM (۲۴ ساعته).")
    lines.append("6. هشتگ‌ها: ۶ تا ۸ هشتگ ترکیبی فارسی و انگلیسی، مرتبط با همان سناریو و پرجستجو برای مخاطب افغان. برای شورت #shorts هم باشد.")
    lines.append("7. شورت: ۴۰ تا ۶۰ ثانیه، هوک قوی در ۳ ثانیه‌ی اول، چرخش طنز در پایان.")
    lines.append("8. ویدیوی طولانی: چند دقیقه‌ای، با ۵ مرحله به ترتیب: هوک، کاشتن نشانه، رسوایی اصلی، واکنش فیزیکی، فرود و دعوت به اقدام.")
    if extra_note:
        lines.append("9. " + extra_note)
    lines.append("")
    lines.append("پاسخ را دقیقاً با همین ساختار JSON بده و هیچ متن اضافه‌ای ننویس:")
    lines.append(SCHEMA)
    return "\n".join(lines)


def call_gemini(prompt):
    headers = {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 8192,
        },
    }
    last_error = None
    for attempt in range(2):
        r = requests.post(GEMINI_URL, headers=headers, json=payload, timeout=120)
        print("Gemini status:", r.status_code)
        if r.status_code != 200:
            print("Gemini response:", r.text[:800])
            r.raise_for_status()
        try:
            data = r.json()
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
            text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(text)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            last_error = e
            print("Could not parse Gemini answer, attempt", attempt + 1, e)
    raise SystemExit("Gemini did not return valid JSON: " + str(last_error))


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
        v["hour_kabul"] = hour_kabul(v["published_at"])

    previous = load_previous()
    history = previous.get("history")
    if history is None:
        history = []
        if previous.get("suggestion"):
            history.append(entry_from(previous["suggestion"], previous.get("generated_at", "")))

    suggestion = call_gemini(build_prompt(videos, history))

    dups = find_duplicates(suggestion, history, videos)
    if dups:
        print("Duplicate title, asking again:", dups)
        note = "این عنوان‌ها تکراری بودند، موضوع کاملاً متفاوتی انتخاب کن: " + " | ".join(dups)
        suggestion = call_gemini(build_prompt(videos, history, note))
        if find_duplicates(suggestion, history, videos):
            print("Warning: duplicate title again")

    suggestion["upload_time_text"] = format_upload_time(suggestion.get("upload_time_kabul", ""))

    now_iso = datetime.now(timezone.utc).isoformat()
    history.append(entry_from(suggestion, now_iso))
    history = history[-MAX_HISTORY:]

    result = {
        "generated_at": now_iso,
        "based_on_videos": [v["title"] for v in videos],
        "suggestion": suggestion,
        "history": history,
    }

    os.makedirs("docs", exist_ok=True)
    with open("docs/suggestion.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    short_title = (suggestion.get("short") or {}).get("title", "")
    print("Suggestion saved:", short_title)


if __name__ == "__main__":
    main()
