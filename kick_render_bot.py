import os
import time
import random
import threading
import requests
from flask import Flask, jsonify

# ====== إعداد المتغيرات مباشرة ======
CLIENT_ID = "01K7QY0JSGSJYM1DY8Z9NPRS85"
CLIENT_SECRET = "4e7dde79c9befe94583eae69029e8d91012e53e59cd4538dd87cad13f7c16ff5"
CHANNEL_ID = "41802318"  # معرف القناة الرقمي
AI_API_KEY = "AIzaSyCSbLWay4_I0Eol9uNezr1qc0T6DICXqTg"  # Google AI Studio API key
AI_URL = ""  # إذا أردت endpoint محدد من Google AI Studio
KICK_API_BASE = "https://kick.com/api/v2"  # API Base

# ====== ضبط السلوك ======
PERSONAS = [
    {"name": "سندس", "style": "لطيفة وتحفيزية", "emoji": "💖"},
    {"name": "ليلى", "style": "مرحة", "emoji": "✨"},
    {"name": "رُبى", "style": "هادئة", "emoji": "🌸"},
    {"name": "نورا", "style": "تشجيعية", "emoji": "🌟"},
    {"name": "جُمان", "style": "تحب GG", "emoji": "🔥"},
    {"name": "عُمر", "style": "مرح", "emoji": "😄"},
    {"name": "سيف", "style": "حماسي", "emoji": "💪"},
    {"name": "كريم", "style": "مهذب", "emoji": "👍"},
    {"name": "رامي", "style": "إيموجي كثير", "emoji": "😂"},
    {"name": "باسل", "style": "هادئ وكول", "emoji": "😎"}
]

SHORT_TEMPLATES = [
    "أحسنت! {emoji}",
    "GG! {emoji}",
    "عمل رائع! {emoji}",
    "واو، ممتاز {emoji}",
    "استمر هكذا! {emoji}"
]

# ====== حالة التوكن والسياق ======
bot_token = None
token_expiry = 0
LAST_SEEN_MESSAGE_ID = None
USER_COOLDOWN = {}

# ====== إعداد Flask ======
app = Flask(__name__)

@app.route("/status")
def status():
    return jsonify({
        "ok": True,
        "bot_token_set": bool(bot_token),
        "channel_id": CHANNEL_ID
    })

# ====== دوال مساعدة ======
def get_app_access_token():
    global bot_token, token_expiry
    url = "https://id.kick.com/oauth/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        r = requests.post(url, data=data, headers=headers, timeout=15)
        r.raise_for_status()
        j = r.json()
        bot_token = j.get("access_token")
        expires_in = int(j.get("expires_in", 3600))
        token_expiry = time.time() + expires_in - 60
        print("حصلنا على BOT_TOKEN بنجاح؛ expires_in:", expires_in)
        return bot_token
    except Exception as e:
        print("فشل الحصول على BOT_TOKEN:", e)
        return None

def ensure_token():
    global bot_token
    if not bot_token or time.time() >= token_expiry:
        return get_app_access_token()
    return bot_token

def send_kick_message(persona, text):
    if not ensure_token():
        return
    url = f"{KICK_API_BASE}/channels/{CHANNEL_ID}/chat/messages"
    headers = {"Authorization": f"Bearer {bot_token}", "Content-Type": "application/json"}
    payload = {"message": f"[{persona['name']}] {text}"}
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code >= 400:
            print("kick postMessage error:", r.status_code, r.text)
        else:
            print(f"إرسال بواسطة {persona['name']}: {text}")
    except Exception as e:
        print("خطأ عند إرسال رسالة إلى Kick:", e)

def ai_generate_short_reply(persona, user_message, user_id):
    if not AI_API_KEY:
        return f"{persona['name']} يقول: {user_message[:30]}... {persona['emoji']}"
    prompt = (
        f"أنت الشخصية \"{persona['name']}\" بأسلوب {persona['style']}. "
        f"تتكلم بالدارجة المغربية أو العربية الفصحى. "
        f"الرد قصير <=30 كلمة. المستخدم قال: \"{user_message}\""
    )
    url = AI_URL or "https://api.aistudio.google.com/v1/generate-text"
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    body = {"prompt": prompt, "max_output_tokens": 60}
    try:
        r = requests.post(url, headers=headers, json=body, timeout=15)
        r.raise_for_status()
        j = r.json()
        reply = j.get("output_text") or j.get("text") or j.get("result") or j.get("generated_text")
        if isinstance(reply, list):
            reply = " ".join(reply)
        if not reply:
            reply = j.get("choices", [{}])[0].get("text", "")
        reply = reply.strip()
        if len(reply.split()) > 40:
            reply = " ".join(reply.split()[:30]) + "..."
        return reply
    except Exception as e:
        print("AI generation error:", e)
        return f"{persona['name']} يقول: {user_message[:30]}... {persona['emoji']}"

USER_RESPONSE_COOLDOWN = 10  # ثواني

def fetch_and_respond():
    global LAST_SEEN_MESSAGE_ID
    while True:
        try:
            if not ensure_token():
                time.sleep(5)
                continue
            headers = {"Authorization": f"Bearer {bot_token}"}
            url = f"{KICK_API_BASE}/channels/{CHANNEL_ID}/chat/messages"
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            data = r.json()
            messages = data.get("messages") or []
            for msg in messages:
                msg_id = msg.get("id")
                user_id = msg.get("user_id") or msg.get("from")
                text = (msg.get("text") or msg.get("message") or "").strip()
                if not text or user_id is None:
                    continue
                if msg.get("is_bot") or msg.get("from_bot"):
                    continue
                if LAST_SEEN_MESSAGE_ID and msg_id <= LAST_SEEN_MESSAGE_ID:
                    continue
                last_time = USER_COOLDOWN.get(user_id, 0)
                if time.time() - last_time < USER_RESPONSE_COOLDOWN:
                    continue
                persona = random.choice(PERSONAS)
                reply = ai_generate_short_reply(persona, text, user_id)
                send_kick_message(persona, reply)
                USER_COOLDOWN[user_id] = time.time()
                LAST_SEEN_MESSAGE_ID = msg_id
        except Exception as e:
            print("Error in fetch_and_respond:", e)
        time.sleep(4)

def random_poster():
    while True:
        persona = random.choice(PERSONAS)
        text = random.choice(SHORT_TEMPLATES).format(emoji=persona["emoji"])
        send_kick_message(persona, text)
        time.sleep(random.randint(8, 15))

if __name__ == "__main__":
    get_app_access_token()
    t1 = threading.Thread(target=random_poster, daemon=True)
    t2 = threading.Thread(target=fetch_and_respond, daemon=True)
    t1.start()
    t2.start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
