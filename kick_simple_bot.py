import os
import requests
from dotenv import load_dotenv

# تحميل القيم من ملف .env
load_dotenv()

CHANNEL_ID = os.getenv("CHANNEL_ID")
SESSION_TOKEN = os.getenv("SESSION_TOKEN")
PERSONA_NAME = os.getenv("PERSONA_NAME")
COMMENT_TEXT = os.getenv("COMMENT_TEXT")

def post_message():
    url = f"https://kick.com/api/v2/channels/{CHANNEL_ID}/chat/messages"
    headers = {
        "Authorization": f"Bearer {SESSION_TOKEN}",
        "Content-Type": "application/json"
    }
    data = {
        "content": f"{PERSONA_NAME}: {COMMENT_TEXT}"
    }
    try:
        response = requests.post(url, headers=headers, json=data, timeout=15)
        response.raise_for_status()
        print("✅ تم الإرسال:", response.json())
    except requests.exceptions.RequestException as e:
        print("❌ خطأ عند إرسال الرسالة:", e)

if __name__ == "__main__":
    print("🚀 بدء Kick Simple Persona Bot")
    post_message()
