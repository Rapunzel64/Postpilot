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

## Accounts and history
Users sign up with a username and password. Passwords are never stored: only a salted hash is saved.
Each account's posts and images are saved to a database, so they are there when the user logs in again.
- Running on your computer: data goes into a local file `postpilot.db` (nothing to set up).
- Deployed online: you MUST use a free MongoDB Atlas database, because the hosting disk is wiped when the app restarts.

### Set up MongoDB Atlas (free)
1. Create an account at https://www.mongodb.com/cloud/atlas and create a free cluster (M0 / "Free").
2. Database Access -> Add New Database User. Choose a username and a password (letters and numbers only keeps it simple).
3. Network Access -> Add IP Address -> "Allow access from anywhere" (0.0.0.0/0). Streamlit Cloud has no fixed IP address.
4. Database -> Connect -> Drivers -> copy the connection string. Replace `<password>` with your database user's password.
5. Put it in the app secrets as MONGODB_URI. A special character in the password (like @ or #) must be written URL-encoded (%40, %23).

## Put it online (Streamlit Community Cloud, free)
1. Upload everything in this folder to a GitHub repository EXCEPT `.env`, `postpilot.db`, `history.json`.
2. At https://share.streamlit.io click Create app, pick the repository, branch `main`, file `app.py`.
3. In Advanced settings -> Secrets paste the contents of `.streamlit/secrets.toml.example` with your real values.
4. Deploy and share the link. Optional secrets: SIGNUP_CODE (invite code) and MAX_GENERATIONS.

## Notes
- Free Gemini tier has limits and may use prompts to improve Google products: don't enter private information.
- The AI picture service (Pollinations) is free but can be slow or unavailable; the app tells you when it is.
