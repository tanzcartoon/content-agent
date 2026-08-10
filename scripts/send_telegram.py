import os
import json
import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    r = requests.post(url, data=payload)
    r.raise_for_status()
    print("Message sent:", r.json().get("ok"))

def build_report():
    with open("docs/data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    main = data["channels"].get("main", {})

    lines = []
    lines.append("📊 <b>گزارش روزانه طنزکارتون</b>")
    lines.append("")
    lines.append(f"👥 مشترکین: {int(main.get('subscribers', 0)):,}")
    lines.append(f"👁 بازدید کل: {int(main.get('views', 0)):,}")
    lines.append(f"🎬 ویدیوها: {main.get('videos', 0)}")
    lines.append("")
    lines.append("🏆 <b>مقایسه با رقبا</b>")

    for key, ch in data["channels"].items():
        if key == "main":
            continue
        title = ch.get("title", key)
        subs = int(ch.get("subscribers", 0))
        lines.append(f"• {title}: {subs:,} مشترک")
    try:
        with open("docs/suggestion.json", "r", encoding="utf-8") as sf:
            sug_data = json.load(sf)
            sug = sug_data.get("suggestion", {})
            lines.append("")
            lines.append("🎬 <b>پیشنهاد سناریوی امروز</b>")
            lines.append(f"📌 {sug.get('title', '')}")
            lines.append(f"🎯 هوک: {sug.get('hook', '')}")
            lines.append(f"📝 {sug.get('scenario', '')}")
            lines.append(f"🔄 چرخش: {sug.get('twist', '')}")
    except (FileNotFoundError, json.JSONDecodeError):
        pass
        
    lines.append("")
    lines.append(f"🕐 بروزرسانی: {data.get('fetched_at', '')}")
    lines.append("🔗 داشبورد: https://tanzcartoon.github.io/content-agent/")

    return "\n".join(lines)

def main():
    if not BOT_TOKEN or not CHAT_ID:
        raise SystemExit("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set")

    report = build_report()
    send_message(report)

if __name__ == "__main__":
    main()
