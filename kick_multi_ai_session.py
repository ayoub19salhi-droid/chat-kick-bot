# kick_multi_ai_proxy.py
# نسخة محدثة: تدعم قائمة بروكسيات (افتراضية + من .env)، تدوير تلقائي عند الفشل.
import os
import time
import random
import requests
import threading
from dotenv import load_dotenv

load_dotenv()

# ====== Environment ======
CHANNEL_ID = os.getenv("CHANNEL_ID", "")
KICK_API_BASE = os.getenv("KICK_API_BASE", "https://kick.com")
SESSION_TOKEN = os.getenv("SESSION_TOKEN", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
AI_URL = os.getenv("AI_URL", "https://api.aistudio.google.com/v1/generate-text")

# Proxy config: either PROXY_URL or PROXY_LIST (csv) in .env
PROXY_URL = os.getenv("PROXY_URL", "")          # single proxy (optional)
PROXY_LIST_ENV = os.getenv("PROXY_LIST", "")    # comma-separated list from .env

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "4"))
RANDOM_POST_MIN = int(os.getenv("RANDOM_POST_MIN", "8"))
RANDOM_POST_MAX = int(os.getenv("RANDOM_POST_MAX", "15"))
USER_COOLDOWN = int(os.getenv("USER_COOLDOWN", "10"))
MAX_CONTEXT = int(os.getenv("MAX_CONTEXT", "10"))

# ====== Default free proxies (placeholders) ======
# ملاحظة: هذه بروكسيات عامة للاختبار فقط — قد تكون ميتة أو بطيئة.
DEFAULT_FREE_PROXIES = [
    "http://51.158.68.68:8811",
    "http://185.199.228.24:8080",
    "http://159.65.69.186:9300",
    "http://194.182.64.53:8080",
    "http://51.79.50.170:9300",
]

# ====== Personas ======
PERSONAS = [
    {"id":"sundus","name":"سندس","style":"لطيفة وتحفيزية","emoji":"💖"},
    {"id":"layla","name":"ليلى","style":"مرحة","emoji":"✨"},
    {"id":"rouba","name":"رُبى","style":"هادئة","emoji":"🌸"},
    {"id":"noura","name":"نورا","style":"تشجيعية","emoji":"🌟"},
    {"id":"juman","name":"جُمان","style":"تحب GG","emoji":"🔥"},
    {"id":"omar","name":"عُمر","style":"مرح","emoji":"😄"},
    {"id":"saif","name":"سيف","style":"حماسي","emoji":"💪"},
    {"id":"karim","name":"كريم","style":"مهذب","emoji":"👍"},
    {"id":"rami","name":"رامي","style":"إيموجي كثير","emoji":"😂"},
    {"id":"bassel","name":"باسل","style":"هادئ وكول","emoji":"😎"},
]

SHORT_TEMPLATES = [
    "أحسنت! {emoji}",
    "GG! {emoji}",
    "عمل رائع! {emoji}",
    "واو، ممتاز {emoji}",
    "استمر هكذا! {emoji}",
]

# ====== state ======
CONTEXT = {}
LAST_SEEN_MESSAGE_ID = None
LAST_REPLY_TIME = {}

# ====== build proxy list ======
PROXY_LIST = []
if PROXY_URL:
    PROXY_LIST.append(PROXY_URL)
if PROXY_LIST_ENV:
    for p in PROXY_LIST_ENV.split(","):
        p = p.strip()
        if p:
            PROXY_LIST.append(p)
# إذا لا توجد proxies في البيئة استخدم الافتراضية
if not PROXY_LIST:
    PROXY_LIST = DEFAULT_FREE_PROXIES.copy()

# normalize: ensure proxies have protocol prefix (http://)
def normalize_proxy(p):
    if p.startswith("http://") or p.startswith("https://"):
        return p
    return "http://" + p

PROXY_LIST = [normalize_proxy(p) for p in PROXY_LIST]

print("Proxy list in use:", PROXY_LIST)

# rotating generator
def proxy_cycle(proxies):
    i = 0
    n = len(proxies)
    while True:
        yield proxies[i % n]
        i += 1

_proxy_iter = proxy_cycle(PROXY_LIST)

def get_next_proxy():
    if not PROXY_LIST:
        return None
    return next(_proxy_iter)

# ====== helpers ======
def build_requests_proxies(proxy_url):
    if not proxy_url:
        return None
    return {"http": proxy_url, "https": proxy_url}

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

# ====== requests with proxy and rotation ======
def post_with_proxy(url, json=None, headers=None, retries=3):
    last_exc = None
    # if no proxies configured, send directly
    if not PROXY_LIST:
        return requests.post(url, json=json, headers=headers, timeout=12)
    for attempt in range(retries):
        proxy = get_next_proxy()
        proxies = build_requests_proxies(proxy)
        try:
            resp = requests.post(url, json=json, headers=headers, timeout=15, proxies=proxies)
            return resp
        except Exception as e:
            last_exc = e
            print(f"Proxy POST failed (attempt {attempt+1}) with proxy={proxy}: {e}")
            time.sleep(1)
    raise last_exc

def get_with_proxy(url, headers=None, retries=3):
    last_exc = None
    if not PROXY_LIST:
        return requests.get(url, headers=headers, timeout=12)
    for attempt in range(retries):
        proxy = get_next_proxy()
        proxies = build_requests_proxies(proxy)
        try:
            resp = requests.get(url, headers=headers, timeout=15, proxies=proxies)
            return resp
        except Exception as e:
            last_exc = e
            print(f"Proxy GET failed (attempt {attempt+1}) with proxy={proxy}: {e}")
            time.sleep(1)
    raise last_exc

# ====== send and fetch ======
def send_kick_message(persona, text):
    if not CHANNEL_ID:
        print("⚠ CHANNEL_ID غير محدد.")
        return False
    post_url = f"{KICK_API_BASE}/api/v2/channels/{CHANNEL_ID}/chat/messages"
    headers = headers_for_persona(persona)
    payload = {"content": f"[{persona['name']}] {text}"}
    try:
        r = post_with_proxy(post_url, json=payload, headers=headers)
        if r.status_code >= 400:
            print(f"kick postMessage error {r.status_code}: {r.text}")
            return False
        print(f"✅ إرسال بواسطة {persona['name']}: {text}")
        return True
    except Exception as e:
        print("❌ خطأ عند إرسال رسالة (post_with_proxy):", e)
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
        r = get_with_proxy(get_url, headers=headers)
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
        print("Error fetching messages from Kick (get_with_proxy):", e)
        return []

# ====== AI ======
def ai_generate_short_reply(persona, user_message):
    if not GOOGLE_API_KEY:
        return random.choice(SHORT_TEMPLATES).format(emoji=persona["emoji"])
    prompt = (
        f"أنت الشخصية \"{persona['name']}\" بأسلوب {persona['style']}. "
        f"تكلم بالدارجة المغربية أو العربية. الرد قصير (<30 كلمة). المستخدم قال: \"{user_message}\"."
    )
    headers = {"Authorization": f"Bearer {GOOGLE_API_KEY}", "Content-Type": "application/json"}
    body = {"prompt": prompt, "max_output_tokens": 60}
    try:
        # use proxy for AI call if proxies configured
        if PROXY_LIST:
            proxy = get_next_proxy()
            proxies = build_requests_proxies(proxy)
            r = requests.post(AI_URL, headers=headers, json=body, timeout=15, proxies=proxies)
        else:
            r = requests.post(AI_URL, headers=headers, json=body, timeout=15)
        r.raise_for_status()
        j = r.json()
        reply = j.get("output_text") or j.get("text") or j.get("generated_text") or ""
        if isinstance(reply, list):
            reply = " ".join(reply)
        reply = (reply or "").strip()
        if len(reply.split()) > 40:
            reply = " ".join(reply.split()[:30]) + "..."
        return reply or random.choice(SHORT_TEMPLATES).format(emoji=persona["emoji"])
    except Exception as e:
        print("AI generation error (with proxy):", e)
        return random.choice(SHORT_TEMPLATES).format(emoji=persona["emoji"])

# ====== loops ======
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
    print("Starting Kick Multi-Persona AI Bot with rotating proxy support")
    if not CHANNEL_ID:
        print("⚠ CHANNEL_ID غير معبأ. أضف CHANNEL_ID في .env أو Environment")
        exit(1)
    if not (SESSION_TOKEN or any(os.getenv(f"{p['id'].upper()}_TOKEN") for p in PERSONAS)):
        print("⚠ لا SESSION_TOKEN عام ولا توكنات شخصية محددة. ضع SESSION_TOKEN أو توكن لكل شخصية.")
    # test message
    test_persona = PERSONAS[0]
    send_kick_message(test_persona, "✅ اختبار: البوت متصل الآن (اختبار مع البروكسي)")
    start_bot_threads()
    while True:
        time.sleep(60)
