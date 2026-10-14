# PostPilot - LinkedIn Content Studio & Automation (Python + Streamlit + Gemini)

PostPilot is an intelligent LinkedIn post generator and automation studio built with Python, Streamlit, and Google Gemini API. It features human-crafted UI design, AI post writing and visual asset generation, 1-click direct publishing to LinkedIn, and automated timing scheduling.

## Run it on your computer
1. Install Python 3.9+ from https://python.org (tick "Add Python to PATH" on Windows).
2. Get a FREE key at https://aistudio.google.com/apikey
3. In a terminal inside this folder:
   ```bash
   python -m pip install -r requirements.txt
   copy .env.example .env        # Mac/Linux: cp .env.example .env
   ```
4. Open `.env` in Notepad and put your key after `GEMINI_API_KEY=`. Save.
   *(Optional)*: Put your `LINKEDIN_ACCESS_TOKEN=` to enable LinkedIn publishing workspace-wide, or connect interactively inside the app!
5. `python -m streamlit run app.py`  (opens http://localhost:8501)

## Key Features
- **Human-Crafted Professional UI**: Clean Slate & LinkedIn Royal Blue aesthetic, realistic LinkedIn post preview cards, and organized tabbed workflow.
- **AI Content Blueprinting**: Templates, tones, custom post lengths, emojis, hashtags, and call-to-actions.
- **Visual Asset Studio**: Six illustration styles with Pollinations AI imagery and Gemini SVG drawings.
- **🚀 1-Click Direct LinkedIn Upload**: Connect your LinkedIn profile and publish text + visual posts directly to your feed.
- **⏰ Automated Timing Scheduling**: Schedule posts for peak engagement times (e.g. 9:00 AM, 1:00 PM, 5:30 PM). A built-in background scheduler daemon publishes them automatically.
- **Queue & History Management**: Live countdowns, cancel/reschedule options, and logs of published posts.
- **Persistent User Accounts**: Data is preserved locally in SQLite (`postpilot.db`) or online via MongoDB Atlas.

## Setting Up Direct LinkedIn Automation
1. Go to the [LinkedIn Developer Portal](https://developer.linkedin.com) and create an App.
2. In the **Products** tab, request access to:
   - **Share on LinkedIn** (`w_member_social`)
   - **Sign In with LinkedIn using OpenID Connect** (`openid`, `profile`)
3. Under **Tools** -> **Token Generator**, generate an Access Token with those permissions.
4. Go to the **🔗 LinkedIn Integration** tab inside PostPilot, paste your token, and click **Verify & Connect**!

## Notes
- Free Gemini tier has limits and may use prompts to improve Google products: avoid entering sensitive personal info.
- The AI picture service (Pollinations) is free but may occasionally be busy; fallback to vector drawings is supported.

## Profile page and sidebar navigation
- The sidebar has a sticky profile card with the signed-in username, saved professional headline/location, LinkedIn connection status, profile page button, and logout action.
- Use **View profile** to open the profile page. Full name, professional headline, location, optional contact email, portfolio URL, skills, and About text can be edited and saved.
- Profile details persist in the configured database: SQLite locally or MongoDB when `MONGODB_URI` is configured.
- The **Create post** button sits above the main hero header so it remains available when the sidebar is collapsed.
- **Content library** is collapsible. It contains separate dropdowns for all posts and favorites, and each post can be expanded to preview, open, or delete it.
- The sidebar uses nested expanders and a keyed container, so install the Streamlit version from `requirements.txt` (`streamlit>=1.50`).

## Run after updating
1. Copy your existing `.env` file from your previous project folder into this folder. Never share that file publicly.
2. Install dependencies: `python -m pip install -r requirements.txt`
3. Run: `python -m streamlit run app.py`
