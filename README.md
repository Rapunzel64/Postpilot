# PostPilot - LinkedIn Post Generator (Python + Streamlit, free Gemini API)

## Run it on your computer
1. Install Python 3.9+ from https://python.org (tick "Add Python to PATH" on Windows).
2. Get a FREE key at https://aistudio.google.com/apikey
3. In a terminal inside this folder:
   ```
   python -m pip install -r requirements.txt
   copy .env.example .env        (Mac/Linux: cp .env.example .env)
   ```
4. Open `.env` in Notepad and put your key after `GEMINI_API_KEY=`. Save.
5. `python -m streamlit run app.py`  (opens http://localhost:8501)

## Features
- Templates, tone, length, emojis, hashtags, call to action
- Edit the generated text, copy it, mark favorites, search history
- Image styles (6) and two image sources: Gemini vector drawing, or a free AI picture (Pollinations)
- Download images as PNG/SVG (vector) or JPG (AI picture)

## Put it online (Streamlit Community Cloud, free)
1. Create a free GitHub account and a new repository. Upload everything in this folder
   EXCEPT `.env` and `history.json` (the included .gitignore already skips them).
2. Go to https://share.streamlit.io, sign in with GitHub, click "Create app",
   choose your repository, branch `main`, main file `app.py`, then Deploy.
3. In the app's menu open Settings -> Secrets and paste the contents of
   `.streamlit/secrets.toml.example` with your real key. Save. The app restarts.
4. Share the app link.

Public apps use YOUR free Gemini quota, so consider setting APP_PASSWORD and/or
MAX_GENERATIONS in the secrets. Set HISTORY_MODE = "session" so visitors never see each other's posts.

## Notes
- Free Gemini tier has limits and may use prompts to improve Google products: don't enter private information.
- The AI picture service (Pollinations) is free but can be slow or unavailable; the app tells you when it is.
