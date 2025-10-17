# kick_multi_ai_session.py
import os
import time
import random
import requests
import threading
from dotenv import load_dotenv

load_dotenv()

# ==== الإعدادات تُقرأ من Environment ====
CLIENT_ID = os.getenv("CLIENT_ID", "")            # (اختياري، يستخدم لتجديد App token)
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "")    # (اختياري)
CHANNEL_ID = os.getenv("CHANNEL_ID", "")          # رقم القناة (مثال: 41802318)
KICK_API_BASE = os.getenv("KICK_API_BASE", "https://kick.com")
SESSION_TOKEN = os.getenv("SESSION_TOKEN", "")    # **ضعها بنفسك** في Render/.env
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")  # مفتاح Google AI Studio
AI_URL = os.getenv("AI_URL", "https://api.aistudio.google.com/v1/generate-text")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "4"))
RANDOM_POST_MIN = int(os.getenv("RANDOM_POST_MIN", "8"))
RANDOM_POST_MAX = int(os.getenv("RANDOM_POST_MAX", "15"))
USER_COOLDOWN = int(os.getenv("USER_COOLDOWN", "10"))
MAX_CONTEXT = int(os.getenv("MAX_CONTEXT", "10"))

# ==== الشخصيات ====
PERSONAS = [
    {"id": "sundus", "name": "سندس", "style": "لطيفة وتحفيزية", "emoji": "💖"},
    {"id": "layla",  "name": "ليلى",  "style": "مرحة",          "emoji": "✨"},
    {"id": "rouba",  "name": "رُبى",  "style": "هادئة",         "emoji": "🌸"},
    {"id": "noura",  "name": "نورا",  "style": "تشجيعية",       "emoji": "🌟"},
    {"id": "juman",  "name": "جُمان", "style": "تحب GG",        "emoji": "🔥"},
    {"id": "omar",   "name": "عُمر",  "style": "مرح",           "emoji": "😄"},
    {"id": "saif",   "name": "سيف",   "style": "حماسي",         "emoji": "💪"},
    {"id": "karim",  "name": "كريم",  "style": "مهذب",          "emoji": "👍"},
    {"id": "rami",   "name": "رامي",  "style": "إيموجي كثير",   "emoji": "😂"},
    {"id": "bassel", "name": "باسل",  "style": "هادئ وكول",     "emoji": "😎"},
]

SHORT_TEMPLATES = [
    "أحسنت! {emoji}",
    "GG! {emoji}",
    "عمل رائع! {emoji}",
    "واو، ممتاز {emoji}",
    "استمر هكذا! {emoji}",
]

# ==== حالة التشغيل ====
CONTEXT = {}
LAST_SEEN_MESSAGE_ID = None
LAST_REPLY_TIME = {}

# ==== دوال مساعدة ====
def persona_token(persona):
    env_name = f"{persona['id'].upper()}_TOKEN"
    return os.getenv(env_name) or None

def headers_for_persona(persona):
    token = persona_token(persona)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; KickBot/1.0)"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif SESSION_TOKEN:
        headers["Cookie"] = f"sessionid={SESSION_TOKEN}"
    headers["Content-Type"] = "application/json"
    return headers

def send_kick_message(persona, text):
    if not CHANNEL_ID:
        print("⚠ CHANNEL_ID غير محدد.")
        return False
    post_url = f"{KICK_API_BASE}/api/v2/channels/{CHANNEL_ID}/chat/messages"
    headers = headers_for_persona(persona)
    payload = {"content": f"[{persona['name']}] {text}"}
    try:
        r = requests.post(post_url, json=payload, headers=headers, timeout=12)
        if r.status_code >= 400:
            print(f"kick postMessage error {r.status_code}: {r.text}")
            return False
        print(f"✅ إرسال بواسطة {persona['name']}: {text}")
        return True
    except Exception as e:
        print("❌ خطأ عند إرسال رسالة إلى Kick:", e)
        return False

def get_messages_from_kick():
    if not CHANNEL_ID:
        return []
    get_url = f"{KICK_API_BASE}/api/v2/channels/{CHANNEL_ID}/chat/messages"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; KickBot/1.0)"}
    if SESSION_TOKEN:
        headers["Cookie"] = f"sessionid={SESSION_TOKEN}"
    else:
        for p in PERSONAS:
            t = persona_token(p)
            if t:
                headers["Authorization"] = f"Bearer {t}"
                break
    try:
        r = requests.get(get_url, headers=headers, timeout=12)
        r.raise_for_status()
        j = r.json()
        msgs = j.get("messages") or j.get("data") or []
        out = []
        for m in msgs:
            msg_id = m.get("id") or m.get("message_id") or m.get("_id")
            user_id = m.get("user_id") or m.get("from") or m.get("author_id")
            text = (m.get("text") or m.get("content") or m.get("message") or "") or ""
            out.append({"id": msg_id, "user_id": user_id, "text": text})
        return out
    except Exception as e:
        print("Error fetching messages from Kick:", e)
        return []

# ==== AI ====
def ai_generate_short_reply(persona, user_message):
    if not GOOGLE_API_KEY:
        return random.choice(SHORT_TEMPLATES).format(emoji=persona["emoji"])
    prompt = (
        f"أنت الشخصية \"{persona['name']}\" بأسلوب {persona['style']}. "
        f"تكلم بالدارجة المغربية أو العربية حسب النص. الرد قصير (<30 كلمة). "
        f"المستخدم قال: \"{user_message}\". أجب بطريقة مشجعة."
    )
    headers = {"Authorization": f"Bearer {GOOGLE_API_KEY}", "Content-Type": "application/json"}
    body = {"prompt": prompt, "max_output_tokens": 60}
    try:
        r = requests.post(AI_URL, headers=headers, json=body, timeout=12)
        r.raise_for_status()
        j = r.json()
        reply = j.get("output_text") or j.get("text") or j.get("generated_text") or ""
        if isinstance(reply, list):
            reply = " ".join(reply)
        reply = reply.strip()
        if len(reply.split()) > 40:
            reply = " ".join(reply.split()[:30]) + "..."
        return reply or random.choice(SHORT_TEMPLATES).format(emoji=persona["emoji"])
    except Exception as e:
        print("AI generation error:", e)
        return random.choice(SHORT_TEMPLATES).format(emoji=persona["emoji"])

# ==== المنطق الرئيسي ====
def fetch_and_respond_loop():
    global LAST_SEEN_MESSAGE_ID
    while True:
        msgs = get_messages_from_kick()
        for m in msgs:
            try:
                mid = m.get("id")
                uid = m.get("user_id")
                text = (m.get("text") or "").strip()
                if not mid or not text:
                    continue
                if LAST_SEEN_MESSAGE_ID and mid <= LAST_SEEN_MESSAGE_ID:
                    continue
                last = LAST_REPLY_TIME.get(uid, 0)
                if time.time() - last < USER_COOLDOWN:
                    continue
                persona = random.choice(PERSONAS)
                reply = ai_generate_short_reply(persona, text)
                ok = send_kick_message(persona, reply)
                if ok:
                    LAST_REPLY_TIME[uid] = time.time()
                    LAST_SEEN_MESSAGE_ID = mid
            except Exception as e:
                print("Error processing message:", e)
        time.sleep(POLL_INTERVAL)

def random_poster_loop():
    time.sleep(3)
    while True:
        persona = random.choice(PERSONAS)
        text = random.choice(SHORT_TEMPLATES).format(emoji=persona["emoji"])
        send_kick_message(persona, text)
        time.sleep(random.randint(RANDOM_POST_MIN, RANDOM_POST_MAX))

def start_bot_threads():
    t1 = threading.Thread(target=random_poster_loop, daemon=True)
    t2 = threading.Thread(target=fetch_and_respond_loop, daemon=True)
    t1.start(); t2.start()
    print("🚀 البوت بدأ: نشر عشوائي واستماع للرسائل")

if __name__ == "__main__":
    print("Starting Kick Multi-Persona AI Bot")
    if not CHANNEL_ID:
        print("⚠ CHANNEL_ID غير معبأ في البيئة. أضف CHANNEL_ID ثم أعد التشغيل.")
        exit(1)
    if not (SESSION_TOKEN or any(os.getenv(f"{p['id'].upper()}_TOKEN") for p in PERSONAS)):
        print("⚠ تحذير: لا SESSION_TOKEN عام ولا توكنات شخصية محددة. ضع SESSION_TOKEN أو توكن لكل شخصية.")
    test_persona = PERSONAS[0]
    send_kick_message(test_persona, "✅ اختبار: البوت متصل الآن (رسالة اختبار)")
    start_bot_threads()
    while True:
        time.sleep(60)
