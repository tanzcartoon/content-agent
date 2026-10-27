import os
import json
import html
import requests
from datetime import datetime, timezone

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SITE_URL = "https://tanzcartoon.github.io/content-agent/"

# اگر سناریوی شورت از این تعداد ساعت قدیمی‌تر باشد، هشدار نشان داده می‌شود.
STALE_SHORT_HOURS = 30
# ویدیوی طولانی فقط تا این تعداد ساعت بعد از ساخته شدن کامل نشان داده می‌شود.
FULL_LONG_HOURS = 20
LONG_PUBLISH_NOTE = "نشر پیشنهادی: شب جمعه"


def esc(value):
    return html.escape(str(value if value is not None else ""))


def hours_since(iso_string):
    try:
        dt = datetime.fromisoformat(str(iso_string).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        return None


def age_text(hours):
    if hours is None:
        return ""
    if hours < 1:
        return "کمتر از یک ساعت"
    if hours < 48:
        return "{} ساعت".format(int(hours))
    return "{} روز".format(int(hours // 24))


def fit(text, limit=3900):
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if "\n" in cut:
        cut = cut[:cut.rfind("\n")]
    return cut


def send_message(text):
    url = "https://api.telegram.org/bot{}/sendMessage".format(BOT_TOKEN)
    payload = {
        "chat_id": CHAT_ID,
        "text": fit(text),
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }
    r = requests.post(url, data=payload, timeout=30)
    if r.status_code != 200:
        print("Telegram error:", r.text[:300])
    r.raise_for_status()
    print("Message sent")


def build_stats_report():
    with open("docs/data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    main = data["channels"].get("main", {})

    lines = []
    lines.append("📊 <b>گزارش روزانه طنزکارتون</b>")
    lines.append("")
    lines.append("👥 مشترکین: {:,}".format(int(main.get("subscribers", 0))))
    lines.append("👁 بازدید کل: {:,}".format(int(main.get("views", 0))))
    lines.append("🎬 ویدیوها: {}".format(main.get("videos", 0)))
    lines.append("")
    lines.append("🏆 <b>مقایسه با رقبا</b>")

    for key, ch in data["channels"].items():
        if key == "main":
            continue
        lines.append("• {}: {:,} مشترک".format(esc(ch.get("title", key)), int(ch.get("subscribers", 0))))

    lines.append("")
    lines.append("🕐 بروزرسانی: " + esc(data.get("fetched_at", "")))
    lines.append("🔗 داشبورد: " + SITE_URL)
    return "\n".join(lines)


def format_tags(tags):
    out = []
    for t in tags or []:
        t = str(t).strip().replace(" ", "_")
        if not t:
            continue
        out.append(t if t.startswith("#") else "#" + t)
    return " ".join(out)


def build_block(label, item, long_form):
    lines = ["<b>{}</b>".format(esc(label))]
    lines.append("📌 " + esc(item.get("title")))
    lines.append("🎯 هوک: " + esc(item.get("hook")))
    lines.append("📝 " + esc(item.get("scenario")))
    if long_form:
        for beat in item.get("beats", []):
            lines.append("▫️ " + esc(beat))
    elif item.get("twist"):
        lines.append("🔄 چرخش: " + esc(item.get("twist")))
    thumb_text = item.get("thumbnail_text")
    thumb_image = item.get("thumbnail_image")
    if thumb_text or thumb_image:
        lines.append("🖼 تامبنیل: «{}» — {}".format(esc(thumb_text), esc(thumb_image)))
    tags = format_tags(item.get("hashtags"))
    if tags:
        lines.append("#️⃣ " + esc(tags))
    return "\n".join(lines)


def build_suggestion_messages():
    try:
        with open("docs/suggestion.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    sug = data.get("suggestion") or {}
    short = sug.get("short")
    long_item = sug.get("long")
    last_error = data.get("last_error")
    base = data.get("generated_at")
    short_age = hours_since(data.get("short_generated_at") or base)
    long_age = hours_since(data.get("long_generated_at") or base)
    stale = short_age is not None and short_age > STALE_SHORT_HOURS

    messages = []
    head = ["🎬 <b>پیشنهاد امروز</b>"]
    if last_error:
        head.append("⚠️ ساخت سناریوی تازه ناموفق بود: " + esc(last_error))
    if stale:
        head.append("⚠️ پیشنهاد شورت مال " + age_text(short_age) + " پیش است و امروز تازه نشده.")
    if short and sug.get("upload_time_text"):
        head.append("⏰ زمان پیشنهادی انتشار شورت: " + esc(sug.get("upload_time_text")))
        if sug.get("upload_reason"):
            head.append(esc(sug.get("upload_reason")))
    if short:
        head.append("")
        head.append(build_block("📱 شورت", short, False))
    if len(head) > 1:
        messages.append("\n".join(head))

    if long_item:
        if long_age is not None and long_age < FULL_LONG_HOURS:
            messages.append(build_block("🎞 ویدیوی طولانی این هفته (تازه) · " + LONG_PUBLISH_NOTE, long_item, True))
        else:
            messages.append(
                "🎞 <b>ویدیوی طولانی این هفته:</b> " + esc(long_item.get("title"))
                + "\n" + esc(LONG_PUBLISH_NOTE)
                + "\n(جزئیات کامل در داشبورد: " + SITE_URL + ")"
            )
    return messages


def main():
    if not BOT_TOKEN or not CHAT_ID:
        raise SystemExit("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")

    send_message(build_stats_report())

    try:
        for message in build_suggestion_messages():
            try:
                send_message(message)
            except Exception as e:
                print("A suggestion message failed:", e.__class__.__name__)
    except Exception as e:
        print("Suggestion messages failed:", e)


if __name__ == "__main__":
    main()
