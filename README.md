# LibTrack AI

AI-powered updater for libraries/frameworks/languages. It fetches real-time info (Serper.dev), summarizes & classifies (Groq), and emails developers (Sender API). Stores registrations in Google Sheets.

## Tech
- Python 3.11, Django 5.x
- gspread + oauth2client (Google Sheets)
- Serper.dev (web search) — `https://google.serper.dev/search`
- Groq (chat completions JSON)
- Sender.net (transactional email, Bearer auth)
- Cron (no Celery)

## Setup

```bash
conda create -n libtrack-ai python=3.11 -y
conda activate libtrack-ai
pip install -r requirements.txt
