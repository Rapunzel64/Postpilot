"""PostPilot - LinkedIn Post Generator & Automation Studio
(Python + Streamlit + free Google Gemini API + LinkedIn Direct Publishing & Scheduling).
"""
import base64
import concurrent.futures as cf
import datetime
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
from urllib.parse import quote, quote_plus, unquote

import requests
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

import linkedin_api
from scheduler import PostScheduler, run_scheduler_daemon

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

TONES = {
    "Professional": "💼",
    "Inspirational": "🌟",
    "Conversational": "💬",
    "Storytelling": "📖",
    "Humorous": "😄",
    "Thought leadership": "🧠"
}
LENGTHS = {
    "Short": ("⚡", "Short (~80 words)"),
    "Medium": ("⭐", "Medium (~150 words)"),
    "Long": ("🏆", "Long (~250 words)")
}
OPTS = {
    "emoji": "😎 Emojis",
    "tags": "#️⃣Hashtags",
    "cta": "📞Call to action",
    "pic": "🖼️Visual creative"
}
STYLES = {
    "Flat gradient": ("🌈", "flat modern vector style with smooth colorful gradients"),
    "Minimal line art": ("✒️", "minimal line-art style with thin strokes, lots of empty space and one accent color"),
    "Neon night": ("🌃", "dark background with glowing neon shapes"),
    "Isometric": ("🧊", "isometric geometric style with layered blocks"),
    "Pastel blobs": ("🍬", "soft pastel organic blobs and flowing waves"),
    "Corporate blue": ("🏢", "clean corporate style in blues and grays"),
}
SOURCES = {
    "vector": "✏️ Vector drawing (Gemini)",
    "ai": "🖼️ AI picture (Pollinations, free)"
}
NONE_TPL = "— Start from scratch —"
TEMPLATES = {
    "🎉 New job / promotion": "I'm starting a new role as [your role] at [company]. Share what excites me about it and thank the people who helped me get here.",
    "🏆 Project completed": "I just completed my project [project name], where I [what you built or did]. Key things I learned: [your learnings].",
    "🎓 Course / certificate": "I completed [course name] and earned [certificate]. The top 3 things I learned: [your points].",
    "💡 Lesson learned": "A lesson I learned the hard way about [topic]: [your story and the takeaway].",
    "🙏 Thank you": "I want to thank [person or team] for [what they did], and what it meant to me.",
    "📣 Event / webinar": "I'm attending/speaking at [event] on [date]. Here is what to expect and why you should join: [details].",
}

st.set_page_config(page_title="PostPilot | LinkedIn Studio", page_icon="🚀", layout="wide")

# Human-crafted UI design system: Slate & LinkedIn Royal Blue palette
st.markdown("""
<style>
/* Base typography & resets */
[data-testid="stButtonGroup"],[data-testid="stButtonGroup"]>div,[data-testid="stButtonGroup"]>div>div{
    flex-wrap:wrap !important;
    overflow:visible !important;
    -webkit-mask-image:none !important;
    mask-image:none !important;
}

/* Hero Header: Human-crafted Slate & LinkedIn Royal Blue Gradient */
.hero {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 55%, #0a66c2 100%);
    color: #ffffff;
    padding: 26px 30px;
    border-radius: 16px;
    margin-bottom: 20px;
    box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.15), 0 8px 10px -6px rgba(10, 102, 194, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.1);
    font-family: "Isometra", serif;
}
.hero h1 {
    color: #ffffff !important;
    margin: 0 0 6px !important;
    padding: 0 !important;
    font-size: 2.05rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em;
    font-family: "Isometra", serif;
}
.hero p {
    margin: 0 !important;
    color: #e2e8f0 !important;
    font-size: 1.02rem !important;
    line-height: 1.5;
    max-width: 720px;
}

/* Sidebar: Modern deep slate */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0b5278 0%, #123c64 25%, #0f172a 66%) !important;
    border-right: 1px solid #1e293b !important;
}
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    background: transparent !important;
}
/* Compact sidebar rhythm: prevent large gaps between navigation sections */
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
    gap: 0.85rem !important;
}
section[data-testid="stSidebar"] [data-testid="stElementContainer"] {
    margin-bottom: 0 !important;
}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    margin-bottom: 0.22rem !important;
    color: white;
}
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3,
section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h4 {
    margin-top: 0.15rem !important;
    margin-bottom: 0.25rem !important;
}
section[data-testid="stSidebar"] hr {
    margin: 0.35rem 0 !important;
    border-color: rgba(148, 163, 184, 0.22) !important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] {
    border: 1px solid rgba(148, 190, 225, 0.25) !important;
    border-radius: 12px !important;
    background: rgba(30, 58, 88, 0.55) !important;
    margin-bottom: 8px !important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary {
    font-weight: 650 !important;
    padding-top: 0.55rem !important;
    padding-bottom: 0.55rem !important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stVerticalBlock"] {
    gap: 0.4rem !important;
}
section[data-testid="stSidebar"] .st-key-sidebar_profile_footer {
    position: sticky;
    bottom: 0;
    z-index: 10;
    background: linear-gradient(180deg, rgba(15,23,42,0.88), #0f172a 20%);
    border-top: 2px solid rgba(148, 163, 184, 0.28);
    padding-top: 8px;
    margin-top: 6px;
}
.profile-mini-card {
    background: rgba(255,255,255,0.09);
    border: 2px solid rgba(191,219,254,0.24);
    border-radius: 13px;
    padding: 12px;
    margin-bottom: 8px;
}
.profile-mini-name { font-weight: 750; font-size: 1rem; color: #f8fafc; }
.profile-mini-handle { font-size: 0.82rem; color: #bfdbfe; overflow-wrap: anywhere; }
.profile-mini-sub { font-size: 0.78rem; color: #cbd5e1; margin-top: 4px; overflow-wrap: anywhere; }
.profile-status { font-size: 0.8rem; margin-top: 7px; }
.profile-page-card {
    background: #ffffff;
    border: 1px solid #dbe5f0;
    border-radius: 16px;
    padding: 22px;
    box-shadow: 0 8px 28px rgba(15,23,42,0.06);
}
section[data-testid="stSidebar"] * {
    color: #f1f5f9;
}
section[data-testid="stSidebar"] input {
    color: #0f172a !important;
    background: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
}
section[data-testid="stSidebar"] .stButton>button {
    background: #1e293b !important;
    color: #e2e8f0 !important;
    border: 1px solid #334155 !important;
    border-radius: 8px !important;
    text-align: left;
    justify-content: flex-start;
    transition: all 0.15s ease-in-out;
}
section[data-testid="stSidebar"] .stButton>button:hover {
    background: #334155 !important;
    border-color: #0a66c2 !important;
    color: #ffffff !important;
}
section[data-testid="stSidebar"] .stButton>button[kind="primary"] {
    background: linear-gradient(135deg, #0a66c2 0%, #0077b5 100%) !important;
    color: #ffffff !important;
    border: none !important;
    font-weight: 600 !important;
    justify-content: center;
    box-shadow: 0 4px 12px rgba(10, 102, 194, 0.3) !important;
}
section[data-testid="stSidebar"] .stButton>button[kind="primary"] * {
    color: #ffffff !important;
}

/* Main action buttons */
div.stButton>button[kind="primary"] {
    background: linear-gradient(135deg, #0a66c2 0%, #0077b5 100%) !important;
    border: 0 !important;
    color: #ffffff !important;
    font-weight: 600 !important;
    width: 100%;
    padding: 0.65rem 1rem !important;
    border-radius: 10px !important;
    box-shadow: 0 4px 14px rgba(10, 102, 194, 0.25) !important;
    transition: all 0.15s ease-in-out !important;
}
div.stButton>button[kind="primary"]:hover {
    background: linear-gradient(135deg, #004182 0%, #0a66c2 100%) !important;
    box-shadow: 0 6px 18px rgba(10, 102, 194, 0.35) !important;
    transform: translateY(-1px);
}

/* Form containers */
div[data-testid="stForm"] {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 22px;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
}
div[data-testid="stFormSubmitButton"] button[kind^="primary"] {
    background: linear-gradient(135deg, #0a66c2 0%, #0077b5 100%) !important;
    border: 0;
    color: #ffffff !important;
    font-weight: 600;
    width: 100%;
    padding: 0.6rem;
    border-radius: 8px;
}

/* Features overview cards */
.feat {
    display: flex;
    gap: 12px;
    align-items: flex-start;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 13px 15px;
    margin-bottom: 11px;
    box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}
.feat span {
    font-size: 1.55rem;
    line-height: 1;
}

/* Authentic LinkedIn Feed Post Preview Card */
.linkedin-post {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    overflow: hidden;
    box-shadow: 0 6px 24px rgba(15, 23, 42, 0.06);
    font-family: -apple-system, system-ui, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    margin-bottom: 16px;
}
.linkedin-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 14px 16px 8px;
}
.linkedin-author {
    display: flex;
    gap: 12px;
    align-items: center;
}
.linkedin-avatar {
    width: 46px;
    height: 46px;
    border-radius: 50%;
    background: linear-gradient(135deg, #0a66c2 0%, #1e293b 100%);
    display: grid;
    place-items: center;
    font-size: 1.3rem;
    color: #ffffff;
    box-shadow: 0 2px 6px rgba(10, 102, 194, 0.2);
}
.linkedin-meta {
    line-height: 1.35;
}
.linkedin-name {
    font-weight: 600;
    font-size: 0.96rem;
    color: #0f172a;
}
.linkedin-sub {
    font-size: 0.8rem;
    color: #64748b;
}
.linkedin-body {
    padding: 12px 16px 14px;
    font-size: 0.96rem;
    line-height: 1.6;
    color: #1e293b;
    word-wrap: break-word;
    white-space: pre-wrap;
}
.linkedin-empty {
    color: #64748b;
    padding: 28px 16px;
    text-align: center;
    font-size: 0.95rem;
}
.linkedin-img {
    width: 100%;
    max-height: 440px;
    object-fit: cover;
    display: block;
    border-top: 1px solid #f1f5f9;
    border-bottom: 1px solid #f1f5f9;
}
.linkedin-stats {
    display: flex;
    justify-content: space-between;
    padding: 8px 16px;
    font-size: 0.8rem;
    color: #64748b;
    border-bottom: 1px solid #f1f5f9;
}
.linkedin-actions {
    display: flex;
    justify-content: space-around;
    padding: 10px 14px;
    color: #475569;
    font-size: 0.88rem;
    font-weight: 500;
}
.linkedin-actions span {
    display: inline-flex;
    align-items: center;
    gap: 4px;
}

/* Status Badges */
.badge-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 0.82rem;
    font-weight: 600;
}
.badge-success { background: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; }
.badge-info { background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
.badge-warning { background: #fffbeb; color: #b45309; border: 1px solid #fde68a; }
.badge-error { background: #fef2f2; color: #b91c1c; border: 1px solid #fecaca; }

/* Clean UI cards */
.ui-card {
    background: #B2BEB5;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 14px;
    box-shadow: 0 2px 8px rgba(15, 23, 42, 0.03);
}

/* Tab bar refinement */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    border-bottom: 1px solid #e2e8f0;
    padding-bottom: 4px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px 8px 0 0;
    padding: 8px 18px;
    font-weight: 600;
    color: #64748b;
}
.stTabs [aria-selected="true"] {
    color: #0a66c2 !important;
    border-bottom: 2px solid #0a66c2 !important;
}
/* ===== Page colour: soft blue-grey (instead of pure white) that matches the sidebar and hero ===== */
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
    background: #E8EEF6 !important;
}
[data-testid="stHeader"] { background: transparent !important; }

/* Streamlit leaves ~6rem of empty space above the first element; keep just enough to clear the top bar */
[data-testid="stMainBlockContainer"], .block-container {
    padding-top: 3.75rem !important;
    padding-bottom: 2.5rem !important;
}
/* The CSS block itself is an invisible element that still adds a gap above the hero */
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] style) { display: none !important; }
/* Hidden helper used to remember the login */
.st-key-cookie_writer { position: absolute; height: 0; width: 0; overflow: hidden; opacity: 0; pointer-events: none; }

/* Form fields: white, with a soft blue-grey border, so they stand out on the tinted page */
[data-testid="stMain"] [data-baseweb="input"],
[data-testid="stMain"] [data-baseweb="base-input"],
[data-testid="stMain"] [data-baseweb="textarea"],
[data-testid="stMain"] [data-baseweb="select"] > div,
[data-testid="stMain"] [data-testid="stTextInputRootElement"],
[data-testid="stMain"] [data-testid="stTextAreaRootElement"] {
    background: #ffffff !important;
    border-color: #c7d3e3 !important;
}
[data-testid="stMain"] textarea, [data-testid="stMain"] input { background: #ffffff !important; }
[data-testid="stMain"] [data-baseweb="input"]:focus-within,
[data-testid="stMain"] [data-baseweb="textarea"]:focus-within,
[data-testid="stMain"] [data-baseweb="select"] > div:focus-within { border-color: #0a66c2 !important; }

/* Option chips (tone, length, include) */
[data-testid="stMain"] button[data-testid="stBaseButton-pills"] {
    background: #ffffff !important;
    border: 1px solid #c7d3e3 !important;
    color: #334155 !important;
}
[data-testid="stMain"] button[data-testid="stBaseButton-pills"]:hover { border-color: #0a66c2 !important; color: #0a66c2 !important; }
[data-testid="stMain"] button[data-testid="stBaseButton-pillsActive"] {
    background: #dbeafe !important;
    border: 1px solid #0a66c2 !important;
    color: #0a4f99 !important;
}
button[data-testid="stBaseButton-segmented_controlActive"] {
    background: #dbeafe !important;
    border-color: #0a66c2 !important;
    color: #0a4f99 !important;
}
[data-baseweb="tab-highlight"] { background-color: #0a66c2 !important; }

/* Buttons and panels */
[data-testid="stMain"] .stButton > button[kind="secondary"],
[data-testid="stMain"] [data-testid="stPopover"] > button,
[data-testid="stMain"] .stDownloadButton > button {
    background: #ffffff !important;
    border: 1px solid #c7d3e3 !important;
    color: #1e293b !important;
}
[data-testid="stMain"] .stButton > button[kind="secondary"]:hover,
[data-testid="stMain"] [data-testid="stPopover"] > button:hover,
[data-testid="stMain"] .stDownloadButton > button:hover { border-color: #0a66c2 !important; color: #0a66c2 !important; }
[data-testid="stMain"] [data-testid="stExpander"] {
    background: #ffffff !important;
    border: 1px solid #d3deec !important;
    border-radius: 12px !important;
}
[data-testid="stMain"] [data-testid="stExpander"] summary { background: transparent !important; }
.stTabs [data-baseweb="tab-list"] { border-bottom-color: #c7d3e3 !important; }
[data-testid="stPopoverBody"] { background: #ffffff !important; border: 1px solid #d3deec !important; }

/* ===== Hero banner that also holds the Create post action ===== */
.st-key-hero_wrap {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 55%, #0a66c2 100%);
    border-radius: 16px;
    padding: 24px 30px;
    margin-bottom: 20px;
    box-shadow: 0 10px 25px -5px rgba(15, 23, 42, 0.15), 0 8px 10px -6px rgba(10, 102, 194, 0.1);
    border: 1px solid rgba(255, 255, 255, 0.1);
    font-family: "Isometra", serif;
}
.st-key-hero_wrap h1 {
    color: #ffffff !important;
    margin: 0 0 6px !important;
    padding: 0 !important;
    font-size: 2.05rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em;
    font-family: "Isometra", serif;
}
.st-key-hero_wrap p {
    margin: 0 !important;
    color: #e2e8f0 !important;
    font-size: 1.02rem !important;
    line-height: 1.5;
    max-width: 720px;
}
.hero-badges { display: flex; justify-content: flex-end; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
.st-key-hero_wrap .st-key-top_create_post .stButton > button[kind="primary"] {
    background: #ffffff !important;
    color: #0a66c2 !important;
    border: 0 !important;
    font-weight: 700 !important;
    box-shadow: 0 4px 14px rgba(2, 6, 23, 0.25) !important;
}
.st-key-hero_wrap .st-key-top_create_post .stButton > button[kind="primary"] * { color: #0a66c2 !important; }
.st-key-hero_wrap .st-key-top_create_post .stButton > button[kind="primary"]:hover {
    background: #e8f1fb !important;
    box-shadow: 0 6px 18px rgba(2, 6, 23, 0.3) !important;
}

/* ===== Sidebar: one navy family with a LinkedIn-blue accent ===== */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #14263f 0%, #0f1b2e 48%, #0b1220 100%) !important;
    border-right: 1px solid rgba(148, 163, 184, 0.16) !important;
}
section[data-testid="stSidebar"] * { color: #e8eef6; }
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"],
section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] * { color: #b4c2d4 !important; opacity: 1 !important; }
section[data-testid="stSidebar"] hr { border-color: rgba(148, 163, 184, 0.16) !important; }

/* Content library: expanders, nested expanders, search box and buttons share one look */
section[data-testid="stSidebar"] [data-testid="stExpander"] {
    background: rgba(255, 255, 255, 0.045) !important;
    border-color: rgba(148, 163, 184, 0.22) !important;
    border-radius: 12px !important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] details,
section[data-testid="stSidebar"] [data-testid="stExpander"] details[open] { background: transparent !important; }
section[data-testid="stSidebar"] [data-testid="stExpander"] summary,
section[data-testid="stSidebar"] [data-testid="stExpander"] details[open] > summary {
    background: transparent !important;
    color: #e8eef6 !important;
    opacity: 1 !important;
    border-radius: 12px !important;
}
section[data-testid="stSidebar"] [data-testid="stExpander"] summary:hover { background: rgba(255, 255, 255, 0.07) !important; }
section[data-testid="stSidebar"] [data-testid="stExpander"] summary *,
section[data-testid="stSidebar"] [data-testid="stExpander"] summary svg { color: #e8eef6 !important; fill: #e8eef6 !important; opacity: 1 !important; }
section[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpander"] { background: rgba(255, 255, 255, 0.04) !important; }
section[data-testid="stSidebar"] [data-testid="stExpanderDetails"] { padding-left: 0.6rem !important; padding-right: 0.6rem !important; }
section[data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button { padding: 0.3rem 0.4rem !important; font-size: 0.82rem !important; white-space: nowrap; }
/* Open / Delete buttons of a saved post: stacked, so the labels are never cut off */
section[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpander"] [data-testid="stHorizontalBlock"] { flex-direction: column !important; gap: 0.4rem !important; }
section[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stExpander"] [data-testid="stColumn"] { width: 100% !important; flex: 1 1 100% !important; min-width: 0 !important; }
section[data-testid="stSidebar"] [data-testid="stTextInputRootElement"],
section[data-testid="stSidebar"] [data-baseweb="input"],
section[data-testid="stSidebar"] [data-baseweb="base-input"] {
    background: rgba(255, 255, 255, 0.07) !important;
    border-color: rgba(148, 163, 184, 0.3) !important;
}
section[data-testid="stSidebar"] input {
    background: transparent !important;
    color: #e8eef6 !important;
    -webkit-text-fill-color: #e8eef6 !important;
    border: 0 !important;
}
section[data-testid="stSidebar"] input::placeholder { color: #8ea0b6 !important; opacity: 1 !important; -webkit-text-fill-color: #8ea0b6 !important; }
section[data-testid="stSidebar"] .stButton > button {
    background: rgba(255, 255, 255, 0.06) !important;
    color: #e8eef6 !important;
    border-color: rgba(148, 163, 184, 0.24) !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(10, 102, 194, 0.3) !important;
    border-color: #4aa3ef !important;
    color: #ffffff !important;
}
section[data-testid="stSidebar"] .stButton > button:disabled { opacity: 0.45 !important; }
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
    background: #0a66c2 !important;
    border-color: #0a66c2 !important;
    box-shadow: 0 4px 14px rgba(10, 102, 194, 0.35) !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover { background: #0b73d9 !important; border-color: #4aa3ef !important; }
section[data-testid="stSidebar"] .st-key-sidebar_profile_footer {
    background: linear-gradient(180deg, rgba(11, 18, 32, 0), #0b1220 24%) !important;
    border-top-color: rgba(148, 163, 184, 0.2) !important;
}
.profile-mini-card { background: rgba(255, 255, 255, 0.06) !important; border-color: rgba(148, 163, 184, 0.24) !important; }
.profile-mini-name { color: #f8fafc !important; }
.profile-mini-handle { color: #7cc0ff !important; }
.profile-mini-sub { color: #aebdd0 !important; }
</style>
""", unsafe_allow_html=True)

S = st.session_state

# ---------- Database and Scheduler setup ----------
def _clean_uri(uri):
    """Fixes common mistakes in MongoDB connection string."""
    uri = uri.strip().strip("\"'").strip()
    m = re.match(r"^(mongodb(?:\+srv)?://)(.*)$", uri)
    if not m or "@" not in m.group(2):
        return uri
    scheme, rest = m.groups()
    at = rest.rfind("@")
    user, sep, pw = rest[:at].partition(":")
    if pw.startswith("<") and pw.endswith(">"):
        pw = pw[1:-1]
    creds = quote_plus(unquote(user)) + (":" + quote_plus(unquote(pw)) if sep else "")
    return f"{scheme}{creds}@{rest[at + 1:]}"


@st.cache_resource
def _mongo():
    from pymongo import MongoClient
    db = MongoClient(_clean_uri(MONGODB_URI), serverSelectionTimeoutMS=8000)[MONGODB_DB]
    db.users.create_index("username", unique=True)
    db.posts.create_index([("username", 1), ("ts", -1)])
    return db


def _lite():
    con = sqlite3.connect(DB_FILE)
    con.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, salt TEXT NOT NULL, pw_hash TEXT NOT NULL, created REAL)")
    con.execute("CREATE TABLE IF NOT EXISTS posts (id TEXT PRIMARY KEY, username TEXT NOT NULL, ts REAL, data TEXT NOT NULL)")
    con.execute("CREATE INDEX IF NOT EXISTS posts_user ON posts(username)")
    con.execute("""CREATE TABLE IF NOT EXISTS auth_sessions (
        token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, expires REAL NOT NULL, created REAL NOT NULL
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS user_profiles (
        username TEXT PRIMARY KEY, full_name TEXT DEFAULT '', headline TEXT DEFAULT '',
        location TEXT DEFAULT '', email TEXT DEFAULT '', website TEXT DEFAULT '',
        skills TEXT DEFAULT '', about TEXT DEFAULT '', updated REAL
    )""")
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
    if len(stored.get("img", "")) > 600000:
        stored["img"] = ""
    if USE_MONGO:
        _mongo().posts.replace_one(
            {"_id": item["id"], "username": u},
            {"_id": item["id"], "username": u, "ts": item["ts"], "item": stored},
            upsert=True
        )
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


def db_get_profile(username):
    """Return editable profile details for a user, without exposing auth secrets."""
    if USE_MONGO:
        doc = _mongo().user_profiles.find_one({"username": username}, {"_id": 0})
        return doc or {}
    rows = _lite_run(
        "SELECT full_name, headline, location, email, website, skills, about FROM user_profiles WHERE username=?",
        (username,), fetch=True
    )
    fields = ("full_name", "headline", "location", "email", "website", "skills", "about")
    return dict(zip(fields, rows[0])) if rows else {}


def db_save_profile(username, profile):
    """Persist profile fields in the configured SQLite or MongoDB database."""
    safe = {k: str(profile.get(k, "") or "").strip() for k in
            ("full_name", "headline", "location", "email", "website", "skills", "about")}
    now = time.time()
    if USE_MONGO:
        _mongo().user_profiles.update_one(
            {"username": username},
            {"$set": {"username": username, **safe, "updated": now}},
            upsert=True
        )
    else:
        _lite_run(
            "INSERT OR REPLACE INTO user_profiles "
            "(username, full_name, headline, location, email, website, skills, about, updated) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (username, safe["full_name"], safe["headline"], safe["location"], safe["email"],
             safe["website"], safe["skills"], safe["about"], now)
        )


# Initialize post scheduler & background worker
scheduler = PostScheduler(DB_FILE, use_mongo=USE_MONGO, mongo_uri=_clean_uri(MONGODB_URI) if USE_MONGO else "", mongo_db=MONGODB_DB)

@st.cache_resource
def _start_background_scheduler():
    return run_scheduler_daemon(scheduler)

_start_background_scheduler()


# ---------- Accounts & Auth ----------
def hash_pw(pw, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt_hex), 200_000).hex()


def log_in(u):
    S.user = u
    S.history = db_load_history(u)


# ---------- Stay signed in on this device ----------
# A random token is stored in a browser cookie. Only its SHA-256 hash is saved in the database, so the
# database never holds a usable token. The token is removed on log out and expires after SESSION_DAYS.
COOKIE_NAME = "postpilot_session"
SESSION_DAYS = 30


def _token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def db_create_session(u):
    token = secrets.token_urlsafe(32)
    now = time.time()
    h = _token_hash(token)
    if USE_MONGO:
        c = _mongo().auth_sessions
        c.delete_many({"expires": {"$lt": now}})
        c.insert_one({"_id": h, "username": u, "expires": now + SESSION_DAYS * 86400, "created": now})
    else:
        _lite_run("DELETE FROM auth_sessions WHERE expires < ?", (now,))
        _lite_run("INSERT INTO auth_sessions VALUES (?,?,?,?)", (h, u, now + SESSION_DAYS * 86400, now))
    return token


def db_session_user(token):
    h = _token_hash(token)
    if USE_MONGO:
        d = _mongo().auth_sessions.find_one({"_id": h})
        return d["username"] if d and d["expires"] > time.time() else None
    rows = _lite_run("SELECT username, expires FROM auth_sessions WHERE token_hash=?", (h,), fetch=True)
    return rows[0][0] if rows and rows[0][1] > time.time() else None


def db_delete_session(token):
    h = _token_hash(token)
    if USE_MONGO:
        _mongo().auth_sessions.delete_one({"_id": h})
    else:
        _lite_run("DELETE FROM auth_sessions WHERE token_hash=?", (h,))


def remember_this_device():
    """Called right after a successful login: creates the token and asks the page to store it as a cookie."""
    try:
        token = db_create_session(S.user)
        S["_session_token"] = token
        S["_set_cookie"] = token
    except Exception:
        pass  # staying signed in is optional, so a database hiccup must not block the login


def try_auto_login():
    """Runs once per browser session: signs the user in again if a valid cookie is present."""
    if S.get("_auto_tried"):
        return
    S["_auto_tried"] = True
    try:
        token = st.context.cookies.get(COOKIE_NAME)
        if token:
            u = db_session_user(token)
            if u and db_get_user(u):
                log_in(u)
                S["_session_token"] = token
    except Exception:
        pass


def emit_cookie(value):
    """Writes (or, with an empty value, removes) the cookie in the browser through a tiny hidden frame."""
    max_age = SESSION_DAYS * 86400 if value else 0
    page = f"""<script>
    (function () {{
      var line = '{COOKIE_NAME}={value}; Path=/; Max-Age={max_age}; SameSite=Lax';
      try {{
        var secure = (window.parent.location.protocol === 'https:') ? '; Secure' : '';
        window.parent.document.cookie = line + secure;
      }} catch (e) {{
        document.cookie = line;
      }}
    }})();
    </script>"""
    with st.container(key="cookie_writer"):
        if hasattr(st, "iframe"):
            st.iframe(page, height=1)
        else:
            components.html(page, height=1)


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
    token = S.get("_session_token")
    if not token:
        try:
            token = st.context.cookies.get(COOKIE_NAME)
        except Exception:
            token = None
    if token:
        try:
            db_delete_session(token)
        except Exception:
            pass
    S.clear()
    S["_clear_cookie"] = True


def auth_page():
    st.markdown('''
    <div class="hero">
        <h1>Welcome to PostPilot 🚀</h1>
        <p>The human-first LinkedIn post generator & automation studio. Create compelling posts, generate visual assets, and automate direct publishing & scheduling.</p>
    </div>
    ''', unsafe_allow_html=True)
    left, right = st.columns([5, 4], gap="large")
    with left:
        st.markdown("### ✨ Designed for Growth & Clarity")
        for ico, title, desc in [
            ("📝", "Engaging LinkedIn Posts", "Tailored tones, hooks, and structures designed for authentic reach."),
            ("🎨", "Automated Visual Assets", "Generate matching AI illustrations and vector visuals seamlessly."),
            ("🚀", "Direct LinkedIn Publishing", "Post directly to your personal LinkedIn profile in one click."),
            ("⏰", "Intelligent Scheduling", "Schedule posts for peak audience hours with background automation."),
            ("💾", "Persistent Cloud History", "Your creations and drafts stay saved securely in your account."),
        ]:
            st.markdown(f'<div class="feat"><span>{ico}</span><div><b>{title}</b><br><span style="color:#64748b;font-size:0.92rem;">{desc}</span></div></div>', unsafe_allow_html=True)
    with right:
        mode = st.segmented_control("Account", ["🔑 Login", "📝 Sign up"], default="🔑 Login",
                                    key="auth_mode", label_visibility="collapsed") or "🔑 Login"
        if mode.endswith("Login"):
            with st.form("login_form"):
                st.markdown("#### 👋 Welcome back")
                u = st.text_input("👤 Username")
                p = st.text_input("🔒 Password", type="password")
                remember = st.checkbox("Keep me signed in on this device", value=True)
                go_login = st.form_submit_button("🔑 Log in", type="primary")
            st.caption("New here? Choose **📝 Sign up** above to create your free account.")
            if go_login:
                err = do_login(u, p)
                if err:
                    st.error(err)
                else:
                    if remember:
                        remember_this_device()
                    st.rerun()
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
                if err:
                    st.error(err)
                else:
                    remember_this_device()
                    st.rerun()
        st.caption("☁️ Online database connected." if USE_MONGO else "💾 Saved locally in postpilot.db.")


if S.pop("_clear_cookie", False):
    emit_cookie("")
if not S.get("user"):
    try_auto_login()
if not S.get("user"):
    auth_page()
    st.stop()
if S.get("_set_cookie"):
    emit_cookie(S.pop("_set_cookie"))

# Session State Defaults
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
S.setdefault("page", "studio")

# Quick date/time session state
now_dt = datetime.datetime.now()
tomorrow_date = (now_dt + datetime.timedelta(days=1)).date()
S.setdefault("sched_date", tomorrow_date)
S.setdefault("sched_time", datetime.time(9, 0))


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


# ---------- Callbacks ----------
def new_post():
    S.page = "studio"
    S.cur, S.post, S.post_edit, S.svg, S.img, S.topic, S.tpl = None, "", "", "", "", "", NONE_TPL


def open_item(pid):
    it = next((x for x in S.history if x["id"] == pid), None)
    if it:
        S.page = "studio"
        S.cur, S.topic, S.tone, S.length = pid, it.get("topic", ""), it.get("tone", "Professional"), it.get("length", "Medium")
        S.post = S.post_edit = it.get("post", "")
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


# ---------- AI Generator Logic ----------
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
        if no_thinking:
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
            break
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
Hashtags: {"end with 5-8 relevant hashtags" if "tags" in opts else "none"}
Call to action: {"end the body with a short question or call to action" if "cta" in opts else "none"}
Rules: start with a strong one-line hook, use short paragraphs separated by blank lines, sound human, thoughtful, and specific (no corporate cliches like "I'm thrilled to announce"), no markdown bold or italics. Output only the post text.""", 2000, no_thinking=True, key=key)


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
    if start != -1 and ">" in last[start:]:
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


def card_html(post, svg, img, author_name="You", author_pic="", author_headline="Creator • PostPilot"):
    """Renders a realistic, human-designed LinkedIn feed preview card."""
    if not post:
        body = '<div class="linkedin-empty">✨ Your generated post will preview here. Draft your topic on the left and click <b>Generate post</b>.</div>'
    else:
        escaped = html.escape(post)
        # Highlight hashtags in LinkedIn Royal Blue
        escaped = re.sub(r"(#[A-Za-z0-9_]+)", r'<span style="color:#0a66c2;font-weight:600;">\1</span>', escaped)
        body = f'<div class="linkedin-body">{escaped.replace(chr(10), "<br>")}</div>'

    src = img or (f"data:image/svg+xml;base64,{base64.b64encode(svg.encode()).decode()}" if svg else "")
    pic = f'<img class="linkedin-img" alt="Illustration for the post" src="{src}">' if src else ""

    if author_pic:
        avatar_html = f'<img src="{author_pic}" style="width:46px;height:46px;border-radius:50%;object-fit:cover;">'
    else:
        avatar_html = '<div class="linkedin-avatar">💼</div>'

    return f'''
    <div class="linkedin-post">
        <div class="linkedin-header">
            <div class="linkedin-author">
                {avatar_html}
                <div class="linkedin-meta">
                    <div class="linkedin-name">{html.escape(author_name)}</div>
                    <div class="linkedin-sub">{html.escape(author_headline)} • Just now • 🌐</div>
                </div>
            </div>
            <div style="color:#94a3b8;font-size:1.15rem;font-weight:bold;">•••</div>
        </div>
        {body}
        {pic}
    </div>
    '''


def png_button(svg):
    b64 = base64.b64encode(svg.encode()).decode()
    page = (f"""<button id="b" style="font:600 13px sans-serif;cursor:pointer;padding:7px 12px;border-radius:6px;border:1px solid #cbd5e1;background:#fff;color:#0f172a">⬇️ Download PNG</button>
<script>
document.getElementById('b').onclick=function(){{var im=new Image();im.onload=function(){{var c=document.createElement('canvas');c.width=1200;c.height=627;c.getContext('2d').drawImage(im,0,0,1200,627);c.toBlob(function(b){{var a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='linkedin-post-image.png';document.body.appendChild(a);a.click();a.remove();}},'image/png');}};im.src='data:image/svg+xml;base64,{b64}';}};
</script>""")
    if hasattr(st, "iframe"):
        st.iframe(page, height=45)
    else:
        components.html(page, height=45)


# Load the current user's profile and LinkedIn connection status
current_username = S.get("user") or ""
user_li = scheduler.get_user_linkedin(current_username) if current_username else {}
has_user_token = bool(user_li.get("linkedin_token") or os.getenv("LINKEDIN_ACCESS_TOKEN"))
li_display_name = user_li.get("linkedin_name") or ("LinkedIn Connected" if has_user_token else "Not connected")
profile_data = db_get_profile(current_username) if current_username else {}
profile_display_name = profile_data.get("full_name") or current_username

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("### 🚀 PostPilot")
    st.caption("L I N K E D I N   S T U D I O")
    st.divider()

    # st.markdown("<p style='color:#7dd3fc;font-size:.78rem;font-weight:800;letter-spacing:.12em;margin:2px 0 4px;'>CREATE</p>", unsafe_allow_html=True)
    st.button("＋  New post", type="primary", on_click=new_post, key="new", use_container_width=True)

    if not (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")):
        st.text_input("🔑 Gemini API key (free)", type="password", key="api_key",
                      help="Or place it in your .env file.")

    st.divider()
    with st.expander("📚 Content library", expanded=False):
        st.text_input("🔎 Search history", key="search", placeholder="Search by topic or keyword...")
        q = S.search.strip().lower()
        matching_posts = [x for x in S.history if not q or q in str(x.get("topic", "")).lower() or q in str(x.get("post", "")).lower()]
        favorite_posts = [x for x in matching_posts if x.get("fav")]

        with st.expander(f"🗂️ All posts · {len(matching_posts)}", expanded=False):
            if not matching_posts:
                st.caption("🌱 Your post history will appear here.")
            for it in matching_posts:
                topic_label = str(it.get("topic") or "Untitled post").strip()
                topic_label = topic_label[:34] + ("…" if len(topic_label) > 34 else "")
                star = "⭐ " if it.get("fav") else "📝 "
                with st.expander(f"{star}{topic_label}", expanded=False):
                    st.caption(str(it.get("post", ""))[:180] + ("…" if len(str(it.get("post", ""))) > 180 else ""))
                    open_col, del_col = st.columns(2)
                    open_col.button("Open post", key=f"open_all_{it['id']}", on_click=open_item, args=(it["id"],), use_container_width=True)
                    del_col.button("🗑️ Delete", key=f"delete_all_{it['id']}", on_click=delete_item, args=(it["id"],), use_container_width=True)

        with st.expander(f"⭐ Favorites · {len(favorite_posts)}", expanded=False):
            if not favorite_posts:
                st.caption("Posts you favorite will appear here.")
            for it in favorite_posts:
                topic_label = str(it.get("topic") or "Untitled post").strip()
                topic_label = topic_label[:34] + ("…" if len(topic_label) > 34 else "")
                with st.expander(f"⭐ {topic_label}", expanded=False):
                    st.caption(str(it.get("post", ""))[:180] + ("…" if len(str(it.get("post", ""))) > 180 else ""))
                    open_col, del_col = st.columns(2)
                    open_col.button("Open post", key=f"open_fav_{it['id']}", on_click=open_item, args=(it["id"],), use_container_width=True)
                    del_col.button("🗑️ Delete", key=f"delete_fav_{it['id']}", on_click=delete_item, args=(it["id"],), use_container_width=True)

        st.button("🧹 Clear all posts", on_click=clear_all, key="clear", use_container_width=True,
                  disabled=not bool(S.history))

    # Sticky account card at the bottom of the sidebar. Connection status and logout live inside it.
    with st.container(key="sidebar_profile_footer"):
        # st.markdown("<p style='color:#7dd3fc;font-size:.78rem;font-weight:800;letter-spacing:.12em;margin-bottom:8px;'>YOUR PROFILE</p>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='profile-mini-card'><div class='profile-mini-name'>👤 {html.escape(profile_display_name)}</div>"
            f"<div class='profile-mini-handle'>@{html.escape(current_username)}</div>"
            f"<div class='profile-mini-sub'>{html.escape(profile_data.get('headline', '')[:58] or 'Add your professional headline')}</div>"
            f"<div class='profile-mini-sub'>{'📍 ' + html.escape(profile_data.get('location', '')[:35]) if profile_data.get('location') else ''}</div>"
            f"<div class='profile-status'>{'🟢 LinkedIn connected · ' + html.escape(li_display_name[:26]) if has_user_token else '🟠 LinkedIn not connected'}</div></div>",
            unsafe_allow_html=True
        )
        st.button("👤 View profile", key="sidebar_profile", use_container_width=True,
                  on_click=lambda: S.__setitem__("page", "profile"))
        st.button("↪ Log out", on_click=logout, key="logout", use_container_width=True)

# Hero banner. The Create post action lives inside it so it stays available when the sidebar is collapsed.
def render_hero(title_html, subtitle_html, badges_html=""):
    with st.container(key="hero_wrap"):
        hero_text, hero_side = st.columns([2.4, 1.8], vertical_alignment="center", gap="large")
        with hero_text:
            st.markdown(f"<h1>{title_html}</h1><p>{subtitle_html}</p>", unsafe_allow_html=True)
        with hero_side:
            if badges_html:
                st.markdown(f'<div class="hero-badges">{badges_html}</div>', unsafe_allow_html=True)
            if st.button("＋  Create post", type="primary", key="top_create_post", use_container_width=True):
                S.page = "studio"
                new_post()
                st.rerun()


if S.get("page") == "profile":
    render_hero("👤 My Profile", "Manage your PostPilot profile details and check your LinkedIn connection.")
    prof_left, prof_right = st.columns([3, 2], gap="large")
    with prof_left:
        st.markdown("### Profile information")
        st.caption("These details are saved to your PostPilot account and can be edited any time.")
        with st.form("profile_details_form"):
            profile_full_name = st.text_input("Full name", value=profile_data.get("full_name", ""), key="profile_full_name", placeholder="e.g. Jane Doe")
            profile_headline = st.text_input("Professional headline", value=profile_data.get("headline", ""), key="profile_headline", placeholder="e.g. Data Science Learner | Python | Machine Learning")
            profile_location = st.text_input("Location", value=profile_data.get("location", ""), key="profile_location", placeholder="City, Country")
            profile_email = st.text_input("Contact email (optional)", value=profile_data.get("email", ""), key="profile_email", placeholder="you@example.com")
            profile_website = st.text_input("Website / portfolio (optional)", value=profile_data.get("website", ""), key="profile_website", placeholder="https://...")
            profile_skills = st.text_input("Skills (comma separated)", value=profile_data.get("skills", ""), key="profile_skills", placeholder="Python, SQL, Machine Learning")
            profile_about = st.text_area("About", value=profile_data.get("about", ""), key="profile_about", height=150, placeholder="Write a short professional introduction...")
            save_profile_clicked = st.form_submit_button("💾 Save profile", type="primary", use_container_width=True)
        if save_profile_clicked:
            try:
                db_save_profile(current_username, {
                    "full_name": profile_full_name, "headline": profile_headline,
                    "location": profile_location, "email": profile_email,
                    "website": profile_website, "skills": profile_skills, "about": profile_about
                })
                st.success("Profile saved successfully.")
                st.rerun()
            except Exception as e:
                st.error(f"Could not save profile: {e}")
    with prof_right:
        st.markdown("### Account")
        with st.container(border=True):
            st.markdown(f"#### 👤 {html.escape(profile_display_name)}")
            st.caption(f"PostPilot username: @{current_username}")
            if profile_data.get("headline"):
                st.write(profile_data["headline"])
            if profile_data.get("location"):
                st.caption(f"📍 {profile_data['location']}")
            st.divider()
            st.markdown("### LinkedIn connection")
            if has_user_token:
                st.success(f"Connected as **{li_display_name}**")
                st.caption("Direct publishing and scheduled posts can use this connection.")
            else:
                st.warning("LinkedIn is not connected yet.")
                st.caption("Open LinkedIn Integration to connect your account.")
            st.caption("To connect or disconnect LinkedIn, return to the Post Studio and open the LinkedIn Integration tab.")
            if st.button("← Back to Post Studio", key="profile_back", use_container_width=True):
                S.page = "studio"
                st.rerun()
    st.stop()

# ---------- Main Workspace Header ----------
u_name = S.get("user") or ""
scheduled_items = scheduler.get_user_scheduled_posts(u_name) if u_name else []
pending_count = sum(1 for x in scheduled_items if x.get("status") == "scheduled")

_hero_badges = (
    ('<span class="badge-pill badge-success">🟢 ' + html.escape(li_display_name) + '</span>' if has_user_token
     else '<span class="badge-pill badge-warning">⚪ LinkedIn Disconnected</span>')
    + f'<span class="badge-pill badge-info">⏰ {pending_count} Scheduled in Queue</span>'
)
render_hero("PostPilot 🚀",
            "Human-crafted LinkedIn Post Studio • AI Writing & Visuals • 1-Click Direct Upload & Automated Scheduling",
            _hero_badges)

# Top navigation tabs for clean separation of concerns
tab_studio, tab_schedule, tab_linkedin = st.tabs([
    "✍️ Post Studio",
    f"📅 Scheduled Queue ({pending_count})",
    "🔗 LinkedIn Integration"
])

# ==================== TAB 1: POST STUDIO ====================
with tab_studio:
    left, right = st.columns([5, 6], gap="large")

    def run(rewrite=False):
        topic = S.topic.strip()
        if not topic:
            st.warning("✍️ Please write your post idea first.")
            return
        if MAX_GENERATIONS and S.gen_count >= MAX_GENERATIONS:
            st.warning("🚦 You've reached the session limit. Please try again later.")
            return
        tone, length, opts = S.tone or "Professional", S.length or "Medium", S.opts or []
        style, source = S.style or "Flat gradient", S.source or "vector"
        key, want_img, vis, img_err = get_key(), "pic" in opts, {"svg": "", "img": ""}, ""
        try:
            with st.spinner("Writing your LinkedIn post and crafting visual..." if want_img else "Writing your LinkedIn post..."):
                with cf.ThreadPoolExecutor(max_workers=2) as ex:
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
            st.error(f"Couldn't create the image: {img_err}")

    def new_image():
        try:
            with st.spinner("🎨 Designing new illustration..."):
                vis = make_visual(S.source or "vector", S.post, S.style or "Flat gradient")
            S.svg, S.img = vis["svg"], vis["img"]
            save_item(svg=S.svg, img=S.img, style=S.style, source=S.source)
        except Exception as e:
            st.error(f"Couldn't create image: {e}")

    with left:
        st.markdown("#### Post Blueprint")
        st.selectbox("📑 Start from a template", [NONE_TPL] + list(TEMPLATES), key="tpl", on_change=apply_template)
        st.text_area("What is your post about?", key="topic", height=130,
                     placeholder="e.g. Led a migration from monolithic architecture to microservices. 3 surprising lessons my engineering team learned along the way...")

        st.markdown("#### 🎭 Voice & Structure")
        st.pills("Tone of voice", list(TONES), key="tone", format_func=lambda t: f"{TONES[t]} {t}")
        st.pills("Length", list(LENGTHS), key="length", format_func=lambda n: f"{LENGTHS[n][0]} {n}")
        st.pills("Include in post", list(OPTS), selection_mode="multi", key="opts", format_func=OPTS.get)

        st.markdown("#### 🎨 Visual Asset")
        s1, s2 = st.columns(2)
        s1.selectbox("Image Style", list(STYLES), key="style", format_func=lambda n: f"{STYLES[n][0]} {n}")
        s2.selectbox("Source", list(SOURCES), key="source", format_func=SOURCES.get)

        go = st.button("✨ Generate LinkedIn Post", type="primary")

        if go:
            run()

        # Refine + publish controls sit right under Generate, so both columns stay about the same height
        if S.post:
            # Secondary Refinement Toolbar
            t1, t2, t3 = st.columns(3)
            rewrite = t1.button("🔄 Rewrite Post", key="rw")
            newimg = t2.button("🎲 New Visual", key="ni")
            cur = current_item()
            fav = bool(cur and cur.get("fav"))
            t3.button("⭐ Saved" if fav else "☆ Favorite", key="fav", on_click=toggle_fav)

            if rewrite:
                run(rewrite=True)
            if newimg:
                new_image()

            st.divider()

            # ---------- Automation Action Hub: Direct Publish & Scheduling ----------
            st.markdown("### 🚀 Publish & Automation Hub")
            
            # Action Card
            pub_col, sched_col = st.columns(2, gap="medium")
            
            # Direct Upload to LinkedIn
            with pub_col:
                st.markdown("##### ⚡ Instant Upload")
                attach_img_pub = st.checkbox("Include visual in post", value=bool(S.img), disabled=not bool(S.img or S.svg), key="pub_attach")
                if st.button("🚀 Publish to LinkedIn Now", type="primary", use_container_width=True, key="btn_pub_now"):
                    active_token = user_li.get("linkedin_token") or os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()
                    if not active_token:
                        st.error("⚠️ LinkedIn account not connected! Please connect in the **🔗 LinkedIn Integration** tab above.")
                    else:
                        with st.spinner("Publishing directly to LinkedIn..."):
                            img_bytes, mime = (None, None)
                            if attach_img_pub and S.img:
                                img_bytes, mime = linkedin_api.extract_image_bytes(S.img)
                            
                            res = linkedin_api.publish_post(
                                token=active_token,
                                text=S.post,
                                image_bytes=img_bytes,
                                mime_type=mime or "image/jpeg",
                                author_urn=user_li.get("linkedin_author")
                            )
                            if res.get("success"):
                                st.success("🎉 Successfully published to LinkedIn!")
                                if hasattr(st, "balloons"):
                                    st.balloons()
                            else:
                                st.error(f"❌ Failed to publish: {res.get('error')}")

            # Schedule Post for Later
            with sched_col:
                st.markdown("##### ⏰ Schedule Upload")
                with st.popover("📅 Set Upload Timing", use_container_width=True):
                    st.markdown("###### Select Date & Time")
                    p_date = st.date_input("Scheduled Date", value=S.sched_date, min_value=datetime.date.today(), key="in_sched_date")
                    p_time = st.time_input("Scheduled Time", value=S.sched_time, key="in_sched_time")
                    
                    st.caption("Quick optimal presets:")
                    q1, q2, q3 = st.columns(3)
                    if q1.button("🌅 9:00 AM", key="q_9am"):
                        S.sched_time = datetime.time(9, 0)
                        st.rerun()
                    if q2.button("☕ 1:00 PM", key="q_1pm"):
                        S.sched_time = datetime.time(13, 0)
                        st.rerun()
                    if q3.button("🌆 5:30 PM", key="q_5pm"):
                        S.sched_time = datetime.time(17, 30)
                        st.rerun()

                    attach_sched = st.checkbox("Attach visual", value=bool(S.img), disabled=not bool(S.img or S.svg), key="sched_attach")
                    
                    if st.button("Confirm & Schedule Post", type="primary", use_container_width=True, key="btn_confirm_sched"):
                        dt_target = datetime.datetime.combine(p_date, p_time)
                        target_ts = dt_target.timestamp()
                        if target_ts <= time.time():
                            st.warning("⚠️ Please select a future date and time.")
                        else:
                            active_token = user_li.get("linkedin_token") or os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()
                            if not active_token:
                                st.warning("⚠️ Note: You need to connect your LinkedIn account in the **LinkedIn Integration** tab before this scheduled post can execute.")
                            
                            scheduler.schedule_post(
                                username=u_name,
                                topic=S.topic or "LinkedIn Post",
                                post=S.post,
                                img=S.img if attach_sched else "",
                                svg=S.svg if attach_sched else "",
                                scheduled_time=target_ts
                            )
                            st.success(f"✅ Scheduled for **{dt_target.strftime('%A, %b %d at %I:%M %p')}**! The background scheduler will post it automatically.")
                            time.sleep(1)
                            st.rerun()

    with right:
        # Realistic Live Preview
        author_display = user_li.get("linkedin_name") or "You"
        headline_display = "LinkedIn Creator • PostPilot" if has_user_token else "Your Headline • PostPilot"
        
        st.markdown(card_html(S.post, S.svg, S.img, author_name=author_display, author_headline=headline_display), unsafe_allow_html=True)
        
        if S.post:
            st.caption(f"📊 Character Count: **{len(S.post)}** / 3,000 characters")

            with st.expander("✏️ Edit Post Content"):
                st.text_area("Make direct edits to the text below", key="post_edit", height=200, on_change=edit_post)
            with st.expander("📋 Copy Post Text"):
                st.code(S.post, language=None, wrap_lines=True)

            if S.img:
                head, _, b64 = S.img.partition(",")
                mime = head[5:].split(";")[0] or "image/jpeg"
                ext = "jpg" if "jpeg" in mime else mime.split("/")[-1]
                st.download_button(f"⬇️ Download Visual ({ext.upper()})", base64.b64decode(b64), f"linkedin-visual.{ext}", mime)
            elif S.svg:
                d1, d2 = st.columns(2)
                d1.download_button("⬇️ Download Visual (SVG)", S.svg, "linkedin-visual.svg", "image/svg+xml")
                with d2:
                    png_button(S.svg)


# ==================== TAB 2: SCHEDULED POSTS QUEUE ====================
with tab_schedule:
    st.markdown("### 📅 Automated Publishing Queue & History")
    all_scheduled = scheduler.get_user_scheduled_posts(u_name) if u_name else []
    
    pending = [x for x in all_scheduled if x.get("status") == "scheduled"]
    completed = [x for x in all_scheduled if x.get("status") in ("published", "failed")]

    m1, m2, m3 = st.columns(3)
    m1.metric("Upcoming Scheduled", len(pending))
    m2.metric("Successfully Published", sum(1 for x in completed if x.get("status") == "published"))
    m3.metric("Failed / Attention Required", sum(1 for x in completed if x.get("status") == "failed"))

    st.markdown("#### ⏳ Active Queue")
    if not pending:
        st.info("No upcoming posts in your queue. Generate a post in the Studio and click **Schedule Upload**!")
    else:
        for idx, item in enumerate(pending):
            pid = item.get("id")
            s_time = item.get("scheduled_time", 0)
            dt_sched = datetime.datetime.fromtimestamp(s_time)
            diff_min = int((s_time - time.time()) / 60)
            
            if diff_min < 0:
                time_label = "⚡ Overdue - Processing in next cycle"
            elif diff_min < 60:
                time_label = f"In {diff_min} minutes"
            elif diff_min < 1440:
                time_label = f"In {diff_min // 60} hours, {diff_min % 60} minutes"
            else:
                time_label = f"On {dt_sched.strftime('%b %d at %I:%M %p')}"

            with st.container(border=True):
                c_head1, c_head2 = st.columns([4, 2])
                c_head1.markdown(f"**{item.get('topic', 'Post')}** &nbsp; <span class='badge-pill badge-info'>{time_label}</span>", unsafe_allow_html=True)
                c_head2.caption(f"Target: {dt_sched.strftime('%Y-%m-%d %H:%M')}")
                
                # Snippet
                post_preview = item.get("post", "")[:180] + ("..." if len(item.get("post", "")) > 180 else "")
                st.write(post_preview)

                btn_col1, btn_col2, _ = st.columns([2, 2, 4])
                if btn_col1.button("🚀 Upload Now", key=f"force_{pid}"):
                    with st.spinner("Posting immediately to LinkedIn..."):
                        res = scheduler.execute_single_post(item)
                        if res.get("success"):
                            st.success("🎉 Post successfully uploaded to LinkedIn!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ Failed: {res.get('error')}")
                
                if btn_col2.button("🗑️ Cancel Schedule", key=f"del_sched_{pid}"):
                    scheduler.delete_scheduled_post(u_name, pid)
                    st.toast("Scheduled post cancelled.")
                    st.rerun()

    if completed:
        st.divider()
        st.markdown("#### 📜 Past Automated Logs")
        for idx, item in enumerate(completed):
            pid = item.get("id")
            st_val = item.get("status")
            pub_time = item.get("published_at") or item.get("scheduled_time")
            dt_str = datetime.datetime.fromtimestamp(pub_time).strftime("%b %d, %Y %I:%M %p") if pub_time else "—"

            with st.container(border=True):
                col_a, col_b = st.columns([5, 1])
                if st_val == "published":
                    badge = "<span class='badge-pill badge-success'>🟢 Published</span>"
                else:
                    badge = f"<span class='badge-pill badge-error'>🔴 Failed: {html.escape(item.get('error_msg', 'Error'))}</span>"
                
                col_a.markdown(f"**{item.get('topic', 'Post')}** &nbsp; {badge} &nbsp; <span style='color:#64748b;font-size:0.85rem;'>({dt_str})</span>", unsafe_allow_html=True)
                col_a.caption(item.get("post", "")[:140] + "...")
                
                if col_b.button("Delete", key=f"del_hist_{pid}"):
                    scheduler.delete_scheduled_post(u_name, pid)
                    st.rerun()


# ==================== TAB 3: LINKEDIN INTEGRATION ====================
with tab_linkedin:
    st.markdown("### 🔗 LinkedIn Connection & Direct Automation")
    st.markdown("Connect your LinkedIn profile to unlock **1-click direct publishing** and **automated background scheduling**.")

    col_l1, col_l2 = st.columns([5, 5], gap="large")

    with col_l1:
        st.markdown("#### 👤 Connection Status")
        active_token = user_li.get("linkedin_token") or os.getenv("LINKEDIN_ACCESS_TOKEN", "").strip()

        if active_token:
            st.success(f"✅ **Connected to LinkedIn as:** {user_li.get('linkedin_name', 'LinkedIn User')}")
            if user_li.get("linkedin_author"):
                st.caption(f"Author URN: `{user_li.get('linkedin_author')}`")

            t_test, t_disc = st.columns(2)
            if t_test.button("🔄 Test LinkedIn Connection", use_container_width=True):
                with st.spinner("Verifying LinkedIn API connection..."):
                    prof = linkedin_api.get_user_profile(active_token)
                    if prof.get("success"):
                        st.success(f"Connection healthy! Verified as **{prof.get('name')}**.")
                    else:
                        st.error(f"Connection test failed: {prof.get('error')}")

            if t_disc.button("Disconnect LinkedIn", use_container_width=True):
                scheduler.clear_user_linkedin(u_name)
                st.toast("LinkedIn account disconnected.")
                time.sleep(1)
                st.rerun()
        else:
            st.warning("⚠️ No LinkedIn account connected yet.")

        st.markdown("---")
        st.markdown("#### 🔑 Connect or Update Access Token")
        token_input = st.text_input(
            "LinkedIn Access Token",
            type="password",
            placeholder="AQED...",
            help="Your personal OAuth 2.0 access token with w_member_social and openid permissions."
        )

        if st.button("🔗 Verify & Connect Account", type="primary", use_container_width=True):
            if not token_input.strip():
                st.warning("Please paste your LinkedIn Access Token.")
            else:
                with st.spinner("Validating token with LinkedIn API..."):
                    prof = linkedin_api.get_user_profile(token_input.strip())
                    if prof.get("success"):
                        scheduler.save_user_linkedin(
                            username=u_name,
                            token=token_input.strip(),
                            author_urn=prof.get("urn", ""),
                            name=prof.get("name", "LinkedIn Member")
                        )
                        st.success(f"🎉 Successfully connected as **{prof.get('name')}**!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"❌ Verification failed: {prof.get('error')}")

    with col_l2:
        st.markdown("#### 📖 How to Get Your LinkedIn Access Token (2 Minutes)")
        with st.container(border=True):
            st.markdown("""
            1. **Create an App:**
               - Visit the [LinkedIn Developer Portal](https://developer.linkedin.com) and log in.
               - Click **Create App**, enter your app name and associate it with any LinkedIn page (or your own).
            
            2. **Enable Required Products:**
               - Under the **Products** tab, add:
                 - **Share on LinkedIn** (provides `w_member_social`)
                 - **Sign In with LinkedIn using OpenID Connect** (provides `openid`, `profile`)
            
            3. **Generate a Token:**
               - Navigate to **Tools** ➔ **Token Generator** (or OAuth 2.0 Tools).
               - Select scopes: `w_member_social`, `openid`, `profile`.
               - Click **Request Access Token**, grant authorization, and copy the generated token.
               - Paste it into the token field on the left and click **Verify & Connect**!
            """)
            st.caption("💡 Tip: You can also set `LINKEDIN_ACCESS_TOKEN` in your `.env` file for default workspace configuration.")
