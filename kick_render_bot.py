# kick_render_bot.py
import os
import time
import random
import threading
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify

load_dotenv()

# ====== إعداد المتغيرات من .env / Render environment ======
CLIENT_ID = os.getenv("CLIENT_ID")            # Optional if you use client_credentials to refresh token
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
CHANNEL_ID = os.getenv("CHANNEL_ID")          # معرف القناة الرقمي
AI_API_KEY = os.getenv("GOOGLE_API_KEY")      # Google AI Studio API key
AI_URL = os.getenv("AI_URL", "")              # ضع هنا endpoint توليد النصوص إذا لازم (مثال من AI Studio)
KICK_API_BASE = os.getenv("KICK_API_BASE", "https://api.kick.com")  # غير إذا اختلف

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

# ====== حالة التوكن والسياق وغيرها ======
bot_token = None
token_expiry = 0
CONTEXT = {}         # { user_id: [msg1, msg2, ...] }
USER_COOLDOWN = {}   # { user_id: timestamp_last_response }
LAST_SEEN_MESSAGE_ID = None

# ====== إعداد Flask لمراقبة الخدمة ======
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
    """
    يجرّب الحصول على App Access Token باستخدام client_credentials.
    يعوّض bot_token وtoken_expiry عالميًا.
    """
    global bot_token, token_expiry
    if not CLIENT_ID or not CLIENT_SECRET:
        print("CLIENT_ID/CLIENT_SECRET غير مضبوطة في المتغيرات.")
        return None
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
    """تأكد أن التوكن موجود وغير منتهي؛ جدد إذا لزم"""
    global bot_token
    if not bot_token or time.time() >= token_expiry:
        print("تجديد/الحصول على BOT_TOKEN...")
        return get_app_access_token()
    return bot_token

def send_kick_message(persona, text):
    """يرسل رسالة إلى قناة Kick باسم البوت (بادئة [اسم الشخصية])"""
    if not ensure_token():
        print("لا يوجد توكن صالح، التخطي.")
        return
    url = f"{KICK_API_BASE}/v1/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {bot_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "channel_id": CHANNEL_ID,
        "message": f"[{persona['name']}] {text}"
    }
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        if r.status_code >= 400:
            print("kick postMessage error:", r.status_code, r.text)
        else:
            print(f"إرسال بواسطة {persona['name']}: {text}")
    except Exception as e:
        print("خطأ عند إرسال رسالة إلى Kick:", e)

def ai_generate_short_reply(persona, user_message, user_id):
    """
    ينشئ ردًا قصيرًا باستخدام Google AI.
    ملاحظة: اضبط AI_URL في المتغيرات حسب توثيق Google AI Studio لديك.
    نطلب صراحة ردًا قصيرًا (<=30 كلمة)، وبالدارجة المغربية/العربية.
    """
    if not AI_API_KEY:
        # fallback سريع إن لم يكن API متاحًا
        return f"{persona['name']} {random.choice(['يقول', 'علق'] )}: {user_message[:20]}... {persona['emoji']}"

    # نجهز prompt موجز يطلب عدم الإطالة
    prompt = (
        f"أنت الشخصية \"{persona['name']}\" بأسلوب {persona['style']}. "
        f"تتكلم بالدارجة المغربية أو العربية الفصحى حسب الرسالة. "
        f"الرد يجب أن يكون **قصيرًا** (جملة واحدة أو عبارتان، أقل من 30 كلمة). "
        f"المستخدم قال: \"{user_message}\". أجب بصورة ودّية ومشجعة."
    )

    # إذا زوّدت AI_URL في المتغيرات استخدمه، وإلا استخدم نقطة نهاية افتراضية يمكن تعديلها
    url = AI_URL or "https://api.aistudio.google.com/v1/generate-text"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }
    body = {
        "prompt": prompt,
        "max_output_tokens": 60  # يضمن إجابة قصيرة
    }
    try:
        r = requests.post(url, headers=headers, json=body, timeout=15)
        r.raise_for_status()
        j = r.json()
        # قد يختلف حقل الإخراج حسب endpoint؛ نحاول عدة مفاتيح شائعة
        reply = j.get("output_text") or j.get("text") or j.get("result") or j.get("generated_text")
        if isinstance(reply, list):
            reply = " ".join(reply)
        if not reply:
            # افتراص إن لم يوجد مفتاح معروف
            reply = j.get("choices", [{}])[0].get("text", "")
        reply = reply.strip()
        # حصر الطول الخروجي
        if len(reply.split()) > 40:
            reply = " ".join(reply.split()[:30]) + "..."
        return reply
    except Exception as e:
        print("AI generation error:", e)
        return f"{persona['name']} يقول: {user_message[:30]}... {persona['emoji']}"

# ====== قائمة بسيطة لمنع السبام: لا نرد للمستخدم إلا كل 10 ثوانٍ ======
USER_RESPONSE_COOLDOWN = 10  # seconds

# ====== دالة الاستماع للرسائل الحية في Kick ======
def fetch_and_respond():
    """
    تستدعي رسائل الشات من Kick وترد على الرسائل الجديدة.
    يعتمد على endpoint GET /v1/chat/messages?channel_id=...
    تأكد من endpoint الصحيح في docs.kick.com — عدّل إذا لزم
    """
    global LAST_SEEN_MESSAGE_ID
    while True:
        try:
            if not ensure_token():
                time.sleep(5); continue
            headers = {"Authorization": f"Bearer {bot_token}"}
            url = f"{KICK_API_BASE}/v1/chat/messages?channel_id={CHANNEL_ID}"
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            data = r.json()
            messages = data.get("messages") or []
            # افحص الرسائل من الأقدم للأحدث
            for msg in messages:
                msg_id = msg.get("id")
                user_id = msg.get("user_id") or msg.get("from")
                text = (msg.get("text") or msg.get("message") or "").strip()
                # تجاهل الرسائل الفارغة أو رسائل البوت نفسه
                if not text or user_id is None:
                    continue
                # تجنب الرد على رسائلنا: يعتمد على صيغ رد API (تعديل حسب docs)
                if msg.get("is_bot") or msg.get("from_bot"):
                    continue
                # عدم الرد على نفس الرسالة مرتين
                if LAST_SEEN_MESSAGE_ID and msg_id <= LAST_SEEN_MESSAGE_ID:
                    continue
                # عزّز شرط البرد
                last_time = USER_COOLDOWN.get(user_id, 0)
                if time.time() - last_time < USER_RESPONSE_COOLDOWN:
                    continue
                # حدّد شخصية عشوائية للرد
                persona = random.choice(PERSONAS)
                reply = ai_generate_short_reply(persona, text, user_id)
                send_kick_message(persona, reply)
                USER_COOLDOWN[user_id] = time.time()
                LAST_SEEN_MESSAGE_ID = msg_id
        except Exception as e:
            print("Error in fetch_and_respond:", e)
        time.sleep(4)  # polling interval (يمكن ضبطه)

# ====== دالة النشر العشوائي المتواصل ======
def random_poster():
    while True:
        persona = random.choice(PERSONAS)
        text = random.choice(SHORT_TEMPLATES).format(emoji=persona["emoji"])
        send_kick_message(persona, text)
        # فاصل عشوائي بين 8 و 15 ثانية (يمكن زيادته إذا تريد سلوك أقل تكرارًا)
        time.sleep(random.randint(8, 15))

# ====== بدء الخيوط وتشغيل Flask ======
if __name__ == "__main__":
    # أول محاولة للحصول على توكن عند الإقلاع
    get_app_access_token()
    # شغل خيط النشر العشوائي وخيط الاستماع
    t1 = threading.Thread(target=random_poster, daemon=True)
    t2 = threading.Thread(target=fetch_and_respond, daemon=True)
    t1.start(); t2.start()
    # شغّل خدمة الويب البسيطة ليبقى Render مسموحاً بإدارة الخدمة
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
