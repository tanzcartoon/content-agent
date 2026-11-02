import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

START_TIME = time.time()
MAX_SECONDS = 20 * 60  # کل زمان مجاز این اسکریپت

YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
CHANNEL_HANDLE = "tanzcartoon"

GEMINI_MODEL = "gemini-3.8-flash"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
YOUTUBE_BASE = "https://www.googleapis.com/youtube/v3"

MAX_HISTORY = 80

# شورت هر روز (به وقت آلمان) تازه می‌شود.
# ویدیوی طولانی هفته‌ای یک‌بار، در این روز هفته (به وقت آلمان):
# 0 دوشنبه، 1 سه‌شنبه، 2 چهارشنبه، 3 پنجشنبه، 4 جمعه، 5 شنبه، 6 یکشنبه
LONG_SUGGEST_WEEKDAY = 1

# برای ساخت اجباری، در Run workflow تیک force را بزن.
FORCE_REGENERATE = os.environ.get("FORCE_REGENERATE", "").strip().lower() == "true"

REQUEST_TIMEOUT = (30, 150)
BUSY_WAITS = [10, 20, 40]
SKIP_WORDS = ("image", "tts", "live", "audio", "embedding", "robotics", "computer", "native", "lite")

# شخصیت‌های ثابت کانال. فقط از همین‌ها استفاده می‌شود.
CHARACTERS = [
    "مادرکلان (حدود ۶۰ ساله، کمی عصبی و گلایه‌مند، با اعصاب خراب سؤال می‌کند)",
    "نواسه (۲۵ ساله، آرام و ملایم، با آرامش جواب می‌دهد)",
    "خانم نواسه (نسترن، ۲۲ ساله)",
    "پدر نواسه (۴۲ ساله)",
    "مادر نواسه (۴۰ ساله)",
]

SHORT_SCHEMA = """  "upload_time_kabul": "18:30",
  "upload_reason": "دلیل انتخاب این ساعت در یک جمله",
  "short": {
    "title": "عنوان شورت",
    "hook": "جمله‌ی هوک ۳ ثانیه‌ی اول",
    "scenario": "شرح سناریو در ۳ تا ۴ جمله، با ذکر نام شخصیت‌ها",
    "twist": "چرخش طنز پایانی",
    "thumbnail_text": "متن کوتاه روی تامبنیل (حداکثر ۴ کلمه)",
    "thumbnail_image": "توصیف تصویر تامبنیل در یک جمله",
    "hashtags": ["#هشتگ۱", "#shorts"]
  }"""

LONG_SCHEMA = """  "long": {
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
  }"""


class ModelUnavailable(Exception):
    pass


def get_zone(name, offset_hours):
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone(timedelta(hours=offset_hours))


KABUL = get_zone("Asia/Kabul", 4.5)
BERLIN = get_zone("Europe/Berlin", 1)


# ---------- یوتیوب ----------

def youtube_get(path, params):
    params = dict(params)
    params["key"] = YOUTUBE_API_KEY
    r = requests.get(YOUTUBE_BASE + path, params=params, timeout=60)
    if r.status_code != 200:
        raise RuntimeError("YouTube API error " + str(r.status_code))
    return r.json()


def get_uploads_playlist(handle):
    data = youtube_get("/channels", {"part": "id,contentDetails", "forHandle": handle})
    items = data.get("items", [])
    if not items:
        return None
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def get_recent_videos(playlist_id, max_results=10):
    data = youtube_get("/playlistItems", {
        "part": "snippet,contentDetails",
        "playlistId": playlist_id,
        "maxResults": max_results,
    })
    videos = []
    for item in data.get("items", []):
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
    data = youtube_get("/videos", {"part": "statistics", "id": ",".join(video_ids)})
    return {item["id"]: item.get("statistics", {}) for item in data.get("items", [])}


# ---------- زمان ----------

def hour_kabul(iso_string):
    try:
        dt = datetime.fromisoformat(iso_string.replace("Z", "+00:00"))
        return dt.astimezone(KABUL).strftime("%H:%M")
    except Exception:
        return "?"


def parse_stamp(value):
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def start_of_today_berlin():
    now_local = datetime.now(BERLIN)
    start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc)


def start_of_last_weekday(weekday):
    now_local = datetime.now(BERLIN)
    days_back = (now_local.weekday() - weekday) % 7
    start = (now_local - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc)


def is_due(stamp, boundary):
    dt = parse_stamp(stamp)
    return dt is None or dt < boundary


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


# ---------- فایل پیشنهاد ----------

def load_previous():
    try:
        with open("docs/suggestion.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_json(data):
    os.makedirs("docs", exist_ok=True)
    with open("docs/suggestion.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def clean_message(text):
    msg = str(text)
    for secret in (YOUTUBE_API_KEY, GEMINI_API_KEY):
        if secret:
            msg = msg.replace(secret, "***")
    return msg[:300]


def record_failure(message):
    data = load_previous()
    data["last_attempt_at"] = datetime.now(timezone.utc).isoformat()
    data["last_error"] = clean_message(message)
    save_json(data)


def valid_short(item):
    return isinstance(item, dict) and bool(item.get("title")) and bool(item.get("scenario"))


def valid_long(item):
    return (
        isinstance(item, dict)
        and bool(item.get("title"))
        and bool(item.get("scenario"))
        and isinstance(item.get("beats"), list)
        and len(item.get("beats")) >= 3
    )


def entry_parts(short_item, long_item, when):
    short_item = short_item or {}
    long_item = long_item or {}
    return {
        "date": when,
        "short_title": short_item.get("title", ""),
        "short_summary": str(short_item.get("scenario", ""))[:150],
        "long_title": long_item.get("title", ""),
        "long_summary": str(long_item.get("scenario", ""))[:150],
    }


def norm(text):
    return "".join(str(text).split()).lower()


def used_titles(history, videos):
    used = set()
    for h in history:
        used.add(norm(h.get("short_title", "")))
        used.add(norm(h.get("long_title", "")))
    for v in videos:
        used.add(norm(v.get("title", "")))
    used.discard("")
    return used


# ---------- پرامپت ----------

def build_prompt(videos, history, need_short, need_long, extra_note=""):
    lines = []
    lines.append("تو دستیار تولید محتوای کانال یوتیوب طنز خانوادگی «طنزکارتون» هستی. مخاطب اصلی کانال مردم افغانستان‌اند.")
    lines.append("کانال هر روز یک شورت و فقط هفته‌ای یک ویدیوی طولانی (شب جمعه) منتشر می‌کند، پس ویدیوی طولانی باید در چند روز قابل فیلم‌برداری باشد.")
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
    needed = []
    if need_short:
        needed.append("شورت (همراه با ساعت پیشنهادی انتشار)")
    if need_long:
        needed.append("ویدیوی طولانی")
    lines.append("این بار فقط این بخش را بساز: " + " و ".join(needed) + ".")
    lines.append("")
    lines.append("قواعد:")
    lines.append("1. همه‌ی متن‌ها به فارسی دری و لهجه‌ی افغانی باشد. از کلمات افغانی استفاده کن (پیسه به جای پول، وخت به جای وقت، گپ، حویلی، موتر، کلکین) و از کلمات ایرانی استفاده نکن.")
    lines.append("2. مادرکلان کمی عصبی گلایه می‌کند و نواسه با آرامش جواب می‌دهد.")
    lines.append("3. موضوع باید کاملاً تازه باشد و با ویدیوهای بالا و فهرست موضوع‌های قبلی تکراری یا شبیه نباشد.")
    lines.append("4. عنوان و تامبنیل باید دقیقاً با محتوای واقعی ویدیو هم‌خوان باشند. عنوان یا تامبنیل گمراه‌کننده بازدید را پایین می‌آورد.")
    lines.append("5. هشتگ‌ها: ۶ تا ۸ هشتگ ترکیبی فارسی و انگلیسی، مرتبط با همان سناریو و پرجستجو برای مخاطب افغان.")
    if need_short:
        lines.append("6. شورت: ۴۰ تا ۶۰ ثانیه، هوک قوی در ۳ ثانیه‌ی اول، چرخش طنز در پایان، و هشتگ #shorts هم باشد.")
        lines.append("7. بهترین ساعت انتشار شورت را از روی جدول بالا (ساعت انتشار در برابر بازدید) انتخاب کن، به وقت افغانستان و با قالب HH:MM (۲۴ ساعته).")
    if need_long:
        lines.append("8. ویدیوی طولانی: چند دقیقه‌ای، با ۵ مرحله به ترتیب: هوک، کاشتن نشانه، رسوایی اصلی، واکنش فیزیکی، فرود و دعوت به اقدام.")
    if extra_note:
        lines.append("9. " + extra_note)
    lines.append("")
    parts = []
    if need_short:
        parts.append(SHORT_SCHEMA)
    if need_long:
        parts.append(LONG_SCHEMA)
    schema = "{\n" + ",\n".join(parts) + "\n}"
    lines.append("پاسخ را دقیقاً با همین ساختار JSON بده و هیچ متن اضافه‌ای ننویس:")
    lines.append(schema)
    return "\n".join(lines)


# ---------- Gemini ----------

def gemini_url(model):
    return GEMINI_BASE + "/models/" + model + ":generateContent"


def gemini_headers():
    return {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"}


def discover_models():
    try:
        r = requests.get(GEMINI_BASE + "/models?pageSize=200", headers=gemini_headers(), timeout=60)
        if r.status_code != 200:
            return []
        found = []
        for m in r.json().get("models", []):
            name = str(m.get("name", "")).replace("models/", "")
            low = name.lower()
            if "generateContent" not in m.get("supportedGenerationMethods", []):
                continue
            if not low.startswith("gemini-") or "flash" not in low:
                continue
            if any(bad in low for bad in SKIP_WORDS):
                continue
            found.append(name)
        found.sort(reverse=True)
        return found
    except Exception as e:
        print("Could not list models:", e.__class__.__name__)
        return []


def check_budget():
    if time.time() - START_TIME > MAX_SECONDS:
        raise RuntimeError("زمان مجاز اجرا تمام شد")


def request_model(model, payload, waits):
    for attempt in range(len(waits) + 1):
        check_budget()
        try:
            r = requests.post(gemini_url(model), headers=gemini_headers(), json=payload, timeout=REQUEST_TIMEOUT)
        except requests.exceptions.RequestException as e:
            print("Gemini request failed:", e.__class__.__name__)
            if attempt < len(waits):
                print("Waiting", waits[attempt], "seconds before retry")
                time.sleep(waits[attempt])
                continue
            raise RuntimeError("Gemini " + model + " did not answer (" + e.__class__.__name__ + ")")
        print("Gemini", model, "status:", r.status_code)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503, 504):
            print("Gemini is busy:", r.text[:200])
            if attempt < len(waits):
                print("Waiting", waits[attempt], "seconds before retry")
                time.sleep(waits[attempt])
                continue
            raise RuntimeError("Gemini " + model + " is busy (HTTP " + str(r.status_code) + ")")
        print("Gemini response:", r.text[:600])
        if r.status_code in (400, 403, 404):
            raise ModelUnavailable("Gemini " + model + " rejected the request (HTTP " + str(r.status_code) + ")")
        raise RuntimeError("Gemini " + model + " error (HTTP " + str(r.status_code) + ")")


def parse_answer(data):
    parts = data["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("answer is not an object")
    return result


def ask_model(model, payload, waits):
    last = None
    for cycle in range(2):
        data = request_model(model, payload, waits)
        try:
            return parse_answer(data)
        except (KeyError, IndexError, TypeError, ValueError) as e:
            last = e
            print("Could not parse answer from", model, "cycle", cycle + 1, e)
            time.sleep(5)
    raise RuntimeError("Unparseable answer from " + model + ": " + str(last))


def call_gemini(prompt):
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "maxOutputTokens": 8192,
        },
    }
    models = [GEMINI_MODEL]
    discovered = False
    errors = []
    index = 0
    while index < len(models):
        model = models[index]
        index += 1
        waits = BUSY_WAITS if index == 1 else [10]
        try:
            result = ask_model(model, payload, waits)
            if model != GEMINI_MODEL:
                print("Used fallback model:", model)
            return result
        except (ModelUnavailable, RuntimeError) as e:
            print("Model failed:", e)
            errors.append(str(e))
            if not discovered:
                discovered = True
                others = [m for m in discover_models() if m != GEMINI_MODEL][:3]
                print("Fallback models:", others)
                models.extend(others)
    raise RuntimeError("All Gemini models failed: " + " | ".join(errors))


def generate_part(videos, history, need_short, need_long):
    key = "short" if need_short else "long"
    validator = valid_short if need_short else valid_long
    note = ""
    last_generated = None
    for attempt in range(2):
        try:
            generated = call_gemini(build_prompt(videos, history, need_short, need_long, note))
        except (RuntimeError, ModelUnavailable):
            if last_generated is not None:
                print("Retry failed, keeping the first answer")
                return last_generated
            raise
        item = generated.get(key)
        if not validator(item):
            if last_generated is not None:
                return last_generated
            raise RuntimeError("پاسخ Gemini برای بخش " + key + " معتبر نبود")
        if norm(item.get("title", "")) in used_titles(history, videos):
            print("Duplicate title:", item.get("title", ""))
            last_generated = generated
            note = "عنوان «" + str(item.get("title", "")) + "» تکراری بود. موضوع کاملاً متفاوتی انتخاب کن."
            continue
        return generated
    return last_generated


# ---------- برنامه‌ی اصلی ----------

def main():
    if not YOUTUBE_API_KEY or not GEMINI_API_KEY:
        raise RuntimeError("Missing YOUTUBE_API_KEY or GEMINI_API_KEY")

    previous = load_previous()
    old_sug = previous.get("suggestion") or {}
    base_stamp = previous.get("generated_at")
    short_stamp = previous.get("short_generated_at") or base_stamp
    long_stamp = previous.get("long_generated_at") or base_stamp

    need_short = (
        FORCE_REGENERATE
        or not valid_short(old_sug.get("short"))
        or is_due(short_stamp, start_of_today_berlin())
    )
    need_long = (
        FORCE_REGENERATE
        or not valid_long(old_sug.get("long"))
        or is_due(long_stamp, start_of_last_weekday(LONG_SUGGEST_WEEKDAY))
    )

    if not need_short and not need_long:
        print("Today's short and this week's long suggestion are already up to date.")
        return

    print("Need new short:", need_short, "| Need new long:", need_long)

    playlist_id = get_uploads_playlist(CHANNEL_HANDLE)
    if not playlist_id:
        raise RuntimeError("Could not resolve channel uploads playlist")

    videos = get_recent_videos(playlist_id)
    if not videos:
        raise RuntimeError("YouTube returned no videos")
    stats = get_video_stats([v["video_id"] for v in videos])
    for v in videos:
        v["views"] = stats.get(v["video_id"], {}).get("viewCount", "0")
        v["hour_kabul"] = hour_kabul(v["published_at"])

    history = previous.get("history")
    if history is None:
        history = []
        if old_sug:
            history.append(entry_parts(old_sug.get("short"), old_sug.get("long"), base_stamp or ""))

    now_iso = datetime.now(timezone.utc).isoformat()
    suggestion = dict(old_sug)
    errors = []
    new_short = None
    new_long = None

    if need_short:
        try:
            generated = generate_part(videos, history, True, False)
            new_short = generated["short"]
            suggestion["short"] = new_short
            suggestion["upload_time_kabul"] = generated.get("upload_time_kabul", "")
            suggestion["upload_reason"] = generated.get("upload_reason", "")
            short_stamp = now_iso
        except (RuntimeError, ModelUnavailable) as e:
            errors.append("شورت: " + str(e))

    if need_long:
        long_history = list(history)
        if new_short:
            long_history.append(entry_parts(new_short, None, now_iso))
        try:
            generated = generate_part(videos, long_history, False, True)
            new_long = generated["long"]
            suggestion["long"] = new_long
            long_stamp = now_iso
        except (RuntimeError, ModelUnavailable) as e:
            errors.append("ویدیوی طولانی: " + str(e))

    if not new_short and not new_long:
        raise RuntimeError(" | ".join(errors) or "no usable sections")

    suggestion["upload_time_text"] = format_upload_time(suggestion.get("upload_time_kabul", ""))

    history.append(entry_parts(new_short, new_long, now_iso))
    history = history[-MAX_HISTORY:]

    error_text = clean_message(" | ".join(errors)) if errors else ""
    result = {
        "generated_at": now_iso,
        "short_generated_at": short_stamp,
        "long_generated_at": long_stamp,
        "last_attempt_at": now_iso,
        "last_error": error_text,
        "based_on_videos": [v["title"] for v in videos],
        "suggestion": suggestion,
        "history": history,
    }
    save_json(result)

    print("Saved. New short:", (new_short or {}).get("title", "-"), "| New long:", (new_long or {}).get("title", "-"))
    if errors:
        raise RuntimeError(" | ".join(errors))


if __name__ == "__main__":
    try:
        main()
    except (Exception, SystemExit) as e:
        message = str(e) or e.__class__.__name__
        print("FAILED:", clean_message(message))
        try:
            record_failure(message)
        except Exception as inner:
            print("Could not record failure:", inner)
        sys.exit(1)
