"""PostPilot - LinkedIn Post Generator (Python + Streamlit + free Google Gemini API)."""
import base64
import concurrent.futures as cf
import hashlib
import hmac
import html
import json
import os
import random
import re
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import quote

import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

load_dotenv()
MODEL = os.getenv("MODEL", "gemini-flash-latest")
# If the main model is busy or missing, these free models are tried next
FALLBACK_MODELS = ["gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
SIGNUP_CODE = os.getenv("SIGNUP_CODE", "")  # optional: people must enter this code to create an account
MONGODB_URI = os.getenv("MONGODB_URI") or ""  # optional online database (needed when deployed)
MONGODB_DB = os.getenv("MONGODB_DB", "postpilot")
USE_MONGO = bool(MONGODB_URI)
DB_FILE = Path(__file__).parent / "postpilot.db"  # used when MongoDB is not set up (local use)
MAX_ITEMS = 30
USERNAME_RE = re.compile(r"^[a-z0-9_.-]{3,30}$")
MAX_GENERATIONS = int(os.getenv("MAX_GENERATIONS", "0") or 0)  # optional: limit per visitor session (0 = unlimited)

TONES = {"Professional": "💼", "Inspirational": "🌟", "Conversational": "💬",
         "Storytelling": "📖", "Humorous": "😄", "Thought leadership": "🧠"}
LENGTHS = {"Short": ("⚡", "Short (~80 words)"), "Medium": ("📝", "Medium (~150 words)"),
           "Long": ("📚", "Long (~250 words)")}
OPTS = {"emoji": "😎 Emojis", "tags": "#️⃣ Hashtags", "cta": "📣 Call to action", "pic": "🖼️ Imaginary image"}
STYLES = {
    "Flat gradient": ("🌈", "flat modern vector style with smooth colorful gradients"),
    "Minimal line art": ("✒️", "minimal line-art style with thin strokes, lots of empty space and one accent color"),
    "Neon night": ("🌃", "dark background with glowing neon shapes"),
    "Isometric": ("🧊", "isometric geometric style with layered blocks"),
    "Pastel blobs": ("🍬", "soft pastel organic blobs and flowing waves"),
    "Corporate blue": ("🏢", "clean corporate style in blues and grays"),
}
SOURCES = {"vector": "✏️ Vector drawing (Gemini)", "ai": "🖼️ AI picture (Pollinations, free)"}
NONE_TPL = "— none —"
TEMPLATES = {
    "🎉 New job / promotion": "I'm starting a new role as [your role] at [company]. Share what excites me about it and thank the people who helped me get here.",
    "🏆 Project completed": "I just completed my project [project name], where I [what you built or did]. Key things I learned: [your learnings].",
    "🎓 Course / certificate": "I completed [course name] and earned [certificate]. The top 3 things I learned: [your points].",
    "💡 Lesson learned": "A lesson I learned the hard way about [topic]: [your story and the takeaway].",
    "🙏 Thank you": "I want to thank [person or team] for [what they did], and what it meant to me.",
    "📣 Event / webinar": "I'm attending/speaking at [event] on [date]. Here is what to expect and why you should join: [details].",
}

st.set_page_config(page_title="PostPilot", page_icon="🚀", layout="wide")

st.markdown("""
<style>
[data-testid="stButtonGroup"],[data-testid="stButtonGroup"]>div,[data-testid="stButtonGroup"]>div>div{flex-wrap:wrap !important;overflow:visible !important;-webkit-mask-image:none !important;mask-image:none !important}
.hero{background:linear-gradient(120deg,#ff4d8d,#7c3aed 55%,#2f7bff);color:#fff;padding:30px 28px;border-radius:20px;margin-bottom:18px;box-shadow:0 12px 32px rgba(76,29,149,.25)}
.hero h1{color:#fff;margin:0 0 6px;padding:0;font-size:2.1rem;line-height:1.15}
.hero p{margin:0;color:rgba(255,255,255,.92);font-size:1.05rem}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#2a0f6b,#4a1fa8 60%,#7a1f8f)}
section[data-testid="stSidebar"] *{color:#fff}
section[data-testid="stSidebar"] input{color:#1c1633}
section[data-testid="stSidebar"] .stButton>button{background:rgba(255,255,255,.12);border:1.5px solid transparent;text-align:left;justify-content:flex-start}
section[data-testid="stSidebar"] .stButton>button:hover{background:rgba(255,255,255,.22);border-color:#ffb020}
section[data-testid="stSidebar"] .stButton>button[kind="primary"]{background:#ffb020;color:#2a1a00;font-weight:700;justify-content:center}
section[data-testid="stSidebar"] .stButton>button[kind="primary"] *{color:#2a1a00}
div.stButton>button[kind="primary"]{background:linear-gradient(120deg,#ff4d8d,#7c3aed 55%,#2f7bff);border:0;color:#fff;font-weight:700;width:100%;padding:.7rem}
.post{background:#fff;border:1px solid #e4dffa;border-radius:16px;overflow:hidden;box-shadow:0 12px 32px rgba(76,29,149,.12)}
.who{display:flex;gap:10px;align-items:center;padding:14px 16px 4px}
.av{width:44px;height:44px;border-radius:50%;background:linear-gradient(120deg,#ff4d8d,#7c3aed,#2f7bff);display:grid;place-items:center;font-size:1.3rem}
.who span{color:#6b6485;font-size:.8rem}
.body{padding:10px 16px 14px;font-size:.97rem;line-height:1.55;word-wrap:break-word}
.empty{color:#6b6485;padding:8px 16px 22px}
.pimg{width:100%;display:block}
.feat{display:flex;gap:12px;align-items:flex-start;background:#fff;border:1px solid #e4dffa;border-radius:14px;padding:12px 14px;margin-bottom:10px;box-shadow:0 6px 18px rgba(76,29,149,.08)}
.feat span{font-size:1.6rem}
div[data-testid="stForm"]{background:#fff;border:1px solid #e4dffa;border-radius:16px;padding:20px;box-shadow:0 12px 32px rgba(76,29,149,.14)}
div[data-testid="stFormSubmitButton"] button[kind^="primary"]{background:linear-gradient(120deg,#ff4d8d,#7c3aed 55%,#2f7bff);border:0;color:#fff;font-weight:700;width:100%;padding:.6rem}
.react{display:flex;justify-content:space-around;padding:10px;border-top:1px solid #e4dffa;color:#6b6485;font-size:.85rem}
</style>
""", unsafe_allow_html=True)

S = st.session_state

# ---------- database: SQLite file on your computer, or MongoDB online ----------
@st.cache_resource
def _mongo():
    from pymongo import MongoClient
    db = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=8000)[MONGODB_DB]
    db.users.create_index("username", unique=True)
    db.posts.create_index([("username", 1), ("ts", -1)])
    return db


def _lite():
    con = sqlite3.connect(DB_FILE)
    con.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, salt TEXT NOT NULL, pw_hash TEXT NOT NULL, created REAL)")
    con.execute("CREATE TABLE IF NOT EXISTS posts (id TEXT PRIMARY KEY, username TEXT NOT NULL, ts REAL, data TEXT NOT NULL)")
    con.execute("CREATE INDEX IF NOT EXISTS posts_user ON posts(username)")
    return con


def _lite_run(sql, args=(), fetch=False):
    con = _lite()
    try:
        cur = con.execute(sql, args)
        rows = cur.fetchall() if fetch else None
        con.commit()
        return rows
    finally:
        con.close()


def db_get_user(u):
    if USE_MONGO:
        return _mongo().users.find_one({"username": u}, {"_id": 0, "username": 1, "salt": 1, "pw_hash": 1})
    rows = _lite_run("SELECT username, salt, pw_hash FROM users WHERE username=?", (u,), fetch=True)
    return dict(zip(("username", "salt", "pw_hash"), rows[0])) if rows else None


def db_create_user(u, salt, pw_hash):
    """Returns False if the username already exists."""
    if USE_MONGO:
        from pymongo.errors import DuplicateKeyError
        try:
            _mongo().users.insert_one({"username": u, "salt": salt, "pw_hash": pw_hash, "created": time.time()})
            return True
        except DuplicateKeyError:
            return False
    try:
        _lite_run("INSERT INTO users VALUES (?,?,?,?)", (u, salt, pw_hash, time.time()))
        return True
    except sqlite3.IntegrityError:
        return False


def db_load_history(u):
    if USE_MONGO:
        docs = _mongo().posts.find({"username": u}, {"item": 1, "_id": 0}).sort("ts", -1).limit(MAX_ITEMS)
        return [d["item"] for d in docs]
    rows = _lite_run("SELECT data FROM posts WHERE username=? ORDER BY ts DESC LIMIT ?", (u, MAX_ITEMS), fetch=True)
    return [json.loads(x[0]) for x in rows]


def db_save_item(u, item):
    stored = dict(item)
    if len(stored.get("img", "")) > 600000:  # keep the database small
        stored["img"] = ""
    if USE_MONGO:
        _mongo().posts.replace_one({"_id": item["id"], "username": u},
                                   {"_id": item["id"], "username": u, "ts": item["ts"], "item": stored}, upsert=True)
    else:
        _lite_run("INSERT OR REPLACE INTO posts VALUES (?,?,?,?)",
                  (item["id"], u, item["ts"], json.dumps(stored, ensure_ascii=False)))


def db_delete_item(u, pid):
    if USE_MONGO:
        _mongo().posts.delete_one({"_id": pid, "username": u})
    else:
        _lite_run("DELETE FROM posts WHERE id=? AND username=?", (pid, u))


def db_clear(u):
    if USE_MONGO:
        _mongo().posts.delete_many({"username": u})
    else:
        _lite_run("DELETE FROM posts WHERE username=?", (u,))


# ---------- accounts ----------
def hash_pw(pw, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), 200_000).hex()


def log_in(u):
    S.user = u
    S.history = db_load_history(u)


def do_signup(u, pw, pw2, code):
    u = (u or "").strip().lower()
    if not USERNAME_RE.match(u):
        return "Username must be 3-30 characters: letters, numbers, dot, dash or underscore."
    if len(pw or "") < 8:
        return "Password must be at least 8 characters."
    if pw != pw2:
        return "The two passwords do not match."
    if SIGNUP_CODE and code != SIGNUP_CODE:
        return "Wrong invite code."
    try:
        salt = secrets.token_hex(16)
        if not db_create_user(u, salt, hash_pw(pw, salt)):
            return "That username is already taken. Try another one, or log in."
        log_in(u)
    except Exception as e:
        return f"Database problem: {e}"
    return ""


def do_login(u, pw):
    now = time.time()
    if S.get("lock_until", 0) > now:
        return f"Too many tries. Please wait {int(S.lock_until - now) + 1} seconds."
    u = (u or "").strip().lower()
    try:
        row = db_get_user(u) if USERNAME_RE.match(u) else None
        ok = hmac.compare_digest(hash_pw(pw or "", row["salt"] if row else "00" * 16), row["pw_hash"] if row else "x")
        if ok:
            S.fails = 0
            log_in(u)
            return ""
    except Exception as e:
        return f"Database problem: {e}"
    S.fails = S.get("fails", 0) + 1
    if S.fails >= 5:
        S.fails, S.lock_until = 0, now + 60
    time.sleep(1)
    return "Wrong username or password."


def logout():
    S.clear()


def auth_page():
    st.markdown('<div class="hero"><h1>Welcome to PostPilot 🚀</h1>'
                '<p>Log in to write LinkedIn posts. Your history is saved to your account, so it is waiting for you every time you come back 🔓.</p></div>',
                unsafe_allow_html=True)
    left, right = st.columns([5, 4], gap="large")
    with left:
        st.markdown("### ✨ What you get")
        for ico, title, desc in [
            ("📝", "Posts in seconds", "Pick a tone and length, and get a ready-to-publish LinkedIn post."),
            ("🎨", "Matching images", "Six image styles, drawn by AI for each post."),
            ("🕘", "History that stays", "All your posts and favorites are saved to your account."),
            ("⭐", "Edit, search, favorite", "Polish the text, search old posts and keep your best ones."),
        ]:
            st.markdown(f'<div class="feat"><span>{ico}</span><div><b>{title}</b><br>{desc}</div></div>', unsafe_allow_html=True)
    with right:
        mode = st.segmented_control("Account", ["🔑 Login", "📝 Sign up"], default="🔑 Login",
                                    key="auth_mode", label_visibility="collapsed") or "🔑 Login"
        if mode.endswith("Login"):
            with st.form("login_form"):
                st.markdown("#### 👋 Welcome back")
                u = st.text_input("👤 Username")
                p = st.text_input("🔒 Password", type="password")
                go_login = st.form_submit_button("🔑 Log in", type="primary")
            st.caption("New here? Choose **📝 Sign up** above to create your free account.")
            if go_login:
                err = do_login(u, p)
                st.error(err) if err else st.rerun()
        else:
            with st.form("signup_form"):
                st.markdown("#### 🎉 Create your account")
                u = st.text_input("👤 Choose a username", help="3-30 characters: letters, numbers, . _ -")
                p = st.text_input("🔒 Choose a password", type="password", help="At least 8 characters")
                p2 = st.text_input("🔁 Repeat the password", type="password")
                code = st.text_input("🎟️ Invite code") if SIGNUP_CODE else ""
                go_sign = st.form_submit_button("🚀 Create account", type="primary")
            st.caption("Already have an account? Choose **🔑 Login** above.")
            if go_sign:
                err = do_signup(u, p, p2, code)
                st.error(err) if err else st.rerun()
        st.caption("☁️ Your account is saved in the online database." if USE_MONGO
                   else "💾 Accounts are saved in a file on this computer (postpilot.db).")


if not S.get("user"):
    auth_page()
    st.stop()

S.setdefault("history", [])
S.setdefault("cur", None)
S.setdefault("post", "")
S.setdefault("post_edit", "")
S.setdefault("svg", "")
S.setdefault("img", "")
S.setdefault("topic", "")
S.setdefault("tone", "Professional")
S.setdefault("length", "Medium")
S.setdefault("opts", list(OPTS))
S.setdefault("style", "Flat gradient")
S.setdefault("source", "vector")
S.setdefault("tpl", NONE_TPL)
S.setdefault("search", "")
S.setdefault("fav_only", False)
S.setdefault("gen_count", 0)


def persist(item):
    try:
        db_save_item(S.user, item)
        extra = S.history[MAX_ITEMS:]
        if extra:
            S.history = S.history[:MAX_ITEMS]
            for x in extra:
                db_delete_item(S.user, x["id"])
    except Exception as e:
        st.warning(f"⚠️ Couldn't save to the database: {e}")


def current_item():
    return next((x for x in S.history if x["id"] == S.cur), None)


def save_item(**patch):
    item = current_item()
    if item is None:
        item = {"id": f"p{int(time.time() * 1000)}{secrets.token_hex(2)}", "ts": time.time()}
        S.cur = item["id"]
        S.history.insert(0, item)
    item.update(patch)
    persist(item)


# ---------- callbacks ----------
def new_post():
    S.cur, S.post, S.post_edit, S.svg, S.img, S.topic, S.tpl = None, "", "", "", "", "", NONE_TPL


def open_item(pid):
    it = next((x for x in S.history if x["id"] == pid), None)
    if it:
        S.cur, S.topic, S.tone, S.length = pid, it["topic"], it["tone"], it["length"]
        S.post = S.post_edit = it["post"]
        S.svg, S.img = it.get("svg", ""), it.get("img", "")
        S.style, S.source = it.get("style", "Flat gradient"), it.get("source", "vector")


def delete_item(pid):
    S.history = [x for x in S.history if x["id"] != pid]
    try:
        db_delete_item(S.user, pid)
    except Exception as e:
        st.warning(f"⚠️ Couldn't delete from the database: {e}")
    if S.cur == pid:
        new_post()


def clear_all():
    S.history = []
    try:
        db_clear(S.user)
    except Exception as e:
        st.warning(f"⚠️ Couldn't clear the database: {e}")
    new_post()


def apply_template():
    if S.tpl != NONE_TPL:
        S.topic = TEMPLATES[S.tpl]


def toggle_fav():
    it = current_item()
    if it:
        it["fav"] = not it.get("fav", False)
        persist(it)


def edit_post():
    S.post = S.post_edit
    if current_item():
        save_item(post=S.post)


# ---------- AI ----------
def get_key():
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or S.get("api_key")


def ask(prompt, max_tokens, no_thinking=False, key=None):
    key = key or get_key()
    if not key or key == "your-api-key-here":
        raise RuntimeError("No API key found. Paste it in the sidebar or add it to your .env file.")
    headers = {"x-goog-api-key": key.strip(), "Content-Type": "application/json"}
    r = None
    for model in [MODEL] + [m for m in FALLBACK_MODELS if m != MODEL]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        cfg = {"maxOutputTokens": max_tokens}
        if no_thinking:  # skip hidden "thinking" so answers arrive much faster
            cfg["thinkingConfig"] = {"thinkingBudget": 0}
        r = None
        for attempt in range(2):
            body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": cfg}
            try:
                r = requests.post(url, headers=headers, json=body, timeout=45)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                r = None
                continue
            if r.status_code == 400 and "thinkingConfig" in cfg:
                cfg.pop("thinkingConfig")
                continue
            if r.status_code in (500, 503) and attempt == 0:
                time.sleep(3)
                continue
            break
        if r is not None and r.status_code == 200:
            break
        if r is not None and r.status_code not in (404, 429, 500, 503):
            break  # a real problem such as a wrong key: other models will not help
    if r is None:
        raise RuntimeError("Gemini took too long to respond. The free service is sometimes busy, so please try again in a moment.")
    if r.status_code != 200:
        try:
            detail = r.json()["error"]["message"]
        except Exception:
            detail = r.text[:200]
        if r.status_code in (500, 503):
            detail = "Google's free servers are busy right now. Please wait a minute and press Generate again."
        elif r.status_code == 429:
            detail = "Free limit reached. Wait about a minute and try again. (" + detail[:120] + ")"
        elif r.status_code in (400, 401, 403) and "key" in detail.lower():
            detail = "The API key was not accepted. Check that you copied the whole key."
        raise RuntimeError(detail)
    try:
        parts = r.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts).strip()
    except Exception:
        text = ""
    if not text:
        raise RuntimeError("The model returned no text (it may have been blocked). Try rewording your idea.")
    return text


def make_post(topic, tone, length, opts, key=None):
    return ask(f"""Write one LinkedIn post about the topic below.
Topic: {topic}
Tone: {tone}
Length: {LENGTHS[length][1]}
Emojis: {"use several relevant emojis, placed naturally" if "emoji" in opts else "none"}
Hashtags: {"end with 3-5 relevant hashtags" if "tags" in opts else "none"}
Call to action: {"end the body with a short question or call to action" if "cta" in opts else "none"}
Rules: start with a strong one-line hook, use short paragraphs separated by blank lines, sound human and specific (no cliches like "I'm thrilled to announce"), no markdown formatting. Output only the post text.""", 2000, no_thinking=True, key=key)


def make_svg(post, key=None, style="Flat gradient"):
    prompt = f"""Draw a simple, colorful illustration for this LinkedIn post as ONE SVG. Reply with only the SVG code, starting with <svg and ending with </svg>. No explanation, no markdown fences.
Rules: viewBox="0 0 1200 627" width="1200" height="627"; style: {STYLES[style][1]}; show one clear visual metaphor for the post's idea using at most 30 simple shapes (rect, circle, ellipse, path, polygon, line); keep the whole SVG under 3500 characters; no photos, no external images or fonts, no scripts; no text.
Post:
{post[:1500]}"""
    last = ""
    for _ in range(2):
        last = ask(prompt, 6000, no_thinking=True, key=key)
        m = re.search(r"<svg[\s\S]*?</svg>", last, re.I)
        if m:
            return re.sub(r"<script[\s\S]*?</script>", "", m.group(0), flags=re.I)
    start = last.lower().find("<svg")
    if start != -1 and ">" in last[start:]:  # cut off: close it so the part drawn still shows
        part = last[start:last.rindex(">") + 1]
        return re.sub(r"<script[\s\S]*?</script>", "", part, flags=re.I) + "</svg>"
    raise RuntimeError("The model did not return a drawing. Reply began with: " + last[:80].replace("\n", " "))


def make_ai_picture(text, style="Flat gradient"):
    """Free AI picture from Pollinations. Returns a data: URI."""
    prompt = f"{STYLES[style][1]}, wide illustration for a LinkedIn post about: {text[:300]}. No text, no letters, no logos."
    url = (f"https://image.pollinations.ai/prompt/{quote(prompt)}?width=1200&height=627&nologo=true"
           f"&model=flux&seed={random.randint(1, 10**6)}")
    last = ""
    for attempt in range(2):
        try:
            r = requests.get(url, timeout=75)
            ctype = r.headers.get("content-type", "")
            if r.status_code == 200 and ctype.startswith("image"):
                return f"data:{ctype.split(';')[0]};base64," + base64.b64encode(r.content).decode()
            last = f"HTTP {r.status_code}"
        except requests.exceptions.RequestException:
            last = "no response"
        if attempt == 0:
            time.sleep(5)
    raise RuntimeError(f"The AI picture service is busy or unavailable ({last}). Try again later, or switch the image source to Vector drawing.")


def make_visual(source, text, style, key=None):
    if source == "ai":
        return {"svg": "", "img": make_ai_picture(text, style)}
    return {"svg": make_svg(text, key, style), "img": ""}


def card_html(post, svg, img):
    if not post:
        body = '<div class="empty">🪄 Your post will appear here. Fill in your idea and press Generate.</div>'
    else:
        body = '<div class="body">' + html.escape(post).replace("\n", "<br>") + "</div>"
    src = img or (f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}" if svg else "")
    pic = f'<img class="pimg" alt="Illustration for the post" src="{src}">' if src else ""
    return ('<div class="post"><div class="who"><div class="av">😊</div><div><b>You</b><br>'
            '<span>Your headline • Just now 🌍</span></div></div>' + body + pic +
            '<div class="react"><span>👍 Like</span><span>💬 Comment</span><span>🔁 Repost</span>'
            '<span>✈️ Send</span></div></div>')


def png_button(svg):
    """Converts the SVG to a PNG inside the browser, so nothing extra needs installing."""
    b64 = base64.b64encode(svg.encode()).decode()
    page = (f"""<button id="b" style="font:600 14px sans-serif;cursor:pointer;padding:8px 14px;border-radius:8px;border:1px solid #d9d2f5;background:#fff;color:#1c1633">⬇️ Download image (PNG)</button>
<script>
document.getElementById('b').onclick=function(){{var im=new Image();im.onload=function(){{var c=document.createElement('canvas');c.width=1200;c.height=627;c.getContext('2d').drawImage(im,0,0,1200,627);c.toBlob(function(b){{var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='linkedin-post-image.png';document.body.appendChild(a);a.click();a.remove();}},'image/png');}};im.src='data:image/svg+xml;base64,{b64}';}};
</script>""")
    if hasattr(st, "iframe"):  # newer Streamlit versions
        st.iframe(page, height=50)
    else:
        components.html(page, height=50)


# ---------- sidebar ----------
with st.sidebar:
    st.markdown("## 🚀 PostPilot")
    u1, u2 = st.columns([3, 2])
    u1.caption(f"👤 **{S.user}**")
    u2.button("🚪 Log out", on_click=logout, key="logout")
    st.button("➕ New post", type="primary", on_click=new_post, key="new")
    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        st.text_input("🔑 Gemini API key (free)", type="password", key="api_key",
                      help="Or put it in a .env file so you don't have to paste it each time.")
    c1, c2 = st.columns([3, 2])
    c1.markdown("**🕘 History**")
    c2.button("Clear all", on_click=clear_all, key="clear")
    st.text_input("🔎 Search history", key="search", placeholder="Type a word...")
    st.toggle("⭐ Favorites only", key="fav_only")
    q = S.search.strip().lower()
    shown = [x for x in S.history
             if (not S.fav_only or x.get("fav")) and (not q or q in x["topic"].lower() or q in x["post"].lower())]
    if not S.history:
        st.caption("🌱 No posts yet. Your creations will show up here.")
    elif not shown:
        st.caption("🔍 Nothing matches.")
    for it in shown:
        a, b = st.columns([5, 1])
        star = "⭐" if it.get("fav") else TONES.get(it["tone"], "📝")
        label = f'{star} {it["topic"][:26]}' + ("…" if len(it["topic"]) > 26 else "")
        a.button(label, key=f'o_{it["id"]}', on_click=open_item, args=(it["id"],))
        b.button("🗑️", key=f'd_{it["id"]}', on_click=delete_item, args=(it["id"],))

# ---------- main ----------
st.markdown('<div class="hero"><h1>Write posts people stop scrolling for ✨</h1>'
            '<p>Share your idea 💡, pick a voice 🎤, and get a polished LinkedIn post with a matching illustration 🎨.</p></div>',
            unsafe_allow_html=True)

left, right = st.columns([5, 6], gap="large")

with left:
    st.subheader("💡 Your idea")
    st.selectbox("📑 Start from a template", [NONE_TPL] + list(TEMPLATES), key="tpl", on_change=apply_template)
    st.text_area("What is the post about?", key="topic", height=140,
                 placeholder="e.g. I was promoted to team lead after 3 years as a developer, and here is what I learned 🙌")
    st.pills("🎭 Tone", list(TONES), key="tone", format_func=lambda t: f"{TONES[t]} {t}")
    st.pills("📏 Length", list(LENGTHS), key="length", format_func=lambda n: f"{LENGTHS[n][0]} {n}")
    st.pills("🎁 Include", list(OPTS), selection_mode="multi", key="opts", format_func=OPTS.get)
    s1, s2 = st.columns(2)
    s1.selectbox("🎨 Image style", list(STYLES), key="style", format_func=lambda n: f"{STYLES[n][0]} {n}")
    s2.selectbox("🖼️ Image source", list(SOURCES), key="source", format_func=SOURCES.get)
    go = st.button("✨ Generate post", type="primary")


def run(rewrite=False):
    topic = S.topic.strip()
    if not topic:
        st.warning("✍️ Please write your idea first.")
        return
    if MAX_GENERATIONS and S.gen_count >= MAX_GENERATIONS:
        st.warning("🚦 You've reached the limit of posts for this session. Please come back later.")
        return
    tone, length, opts = S.tone or "Professional", S.length or "Medium", S.opts or []
    style, source = S.style or "Flat gradient", S.source or "vector"
    key, want_img, vis, img_err = get_key(), "pic" in opts, {"svg": "", "img": ""}, ""
    try:
        with st.spinner("✍️ Writing your post and drawing the image..." if want_img else "✍️ Writing your post..."):
            with cf.ThreadPoolExecutor(max_workers=2) as ex:  # post and image are made at the same time
                f_post = ex.submit(make_post, topic, tone, length, opts, key)
                f_img = ex.submit(make_visual, source, topic, style, key) if want_img else None
                post = f_post.result()
                if f_img:
                    try:
                        vis = f_img.result()
                    except Exception as e:
                        img_err = str(e)
    except Exception as e:
        st.error(f"⚠️ {e}")
        return
    S.gen_count += 1
    if not rewrite:
        S.cur = None
    S.post = S.post_edit = post
    S.svg, S.img = vis["svg"], vis["img"]
    save_item(topic=topic, tone=tone, length=length, post=post, svg=S.svg, img=S.img, style=style, source=source)
    if img_err:
        st.error(f"😕 Couldn't create the image: {img_err}")


def new_image():
    try:
        with st.spinner("🎨 Imagining an illustration..."):
            vis = make_visual(S.source or "vector", S.post, S.style or "Flat gradient")
        S.svg, S.img = vis["svg"], vis["img"]
        save_item(svg=S.svg, img=S.img, style=S.style, source=S.source)
    except Exception as e:
        st.error(f"😕 Couldn't create the image: {e}")


if go:
    with left:
        run()

with right:
    t1, t2, t3 = st.columns(3)
    rewrite = t1.button("🔄 Rewrite", disabled=not S.post, key="rw")
    newimg = t2.button("🎲 New image", disabled=not S.post, key="ni")
    cur = current_item()
    fav = bool(cur and cur.get("fav"))
    t3.button("⭐ Saved" if fav else "☆ Favorite", disabled=not cur, key="fav", on_click=toggle_fav)
    if rewrite:
        with left:
            run(rewrite=True)
    if newimg:
        new_image()
    if S.post:
        st.caption(f"📊 {len(S.post)} / 3,000 characters")
    st.markdown(card_html(S.post, S.svg, S.img), unsafe_allow_html=True)
    if S.post:
        with st.expander("✏️ Edit the post text"):
            st.text_area("Change anything, then click outside the box to apply", key="post_edit", height=220, on_change=edit_post)
        with st.expander("📋 Copy the post text"):
            st.code(S.post, language=None, wrap_lines=True)
    if S.img:
        head, _, b64 = S.img.partition(",")
        mime = head[5:].split(";")[0] or "image/jpeg"
        st.download_button("⬇️ Download image", base64.b64decode(b64), "linkedin-post-image." + mime.split("/")[-1].replace("jpeg", "jpg"), mime)
    elif S.svg:
        d1, d2 = st.columns(2)
        d1.download_button("⬇️ Download image (SVG)", S.svg, "linkedin-post-image.svg", "image/svg+xml")
        with d2:
            png_button(S.svg)
