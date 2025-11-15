import os
import requests
from dotenv import load_dotenv
from pathlib import Path


# ✅ Find .env manually
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"
print("Loading env from:", env_path)

load_dotenv(dotenv_path=env_path)

API_KEY = os.getenv("SERPER_API_KEY")
print("Loaded SERPER_API_KEY:", API_KEY)

if not API_KEY:
    raise RuntimeError("SERPER_API_KEY is missing")

url = "https://google.serper.dev/search"
headers = {
    "X-API-KEY": API_KEY,
    "Content-Type": "application/json",
}
payload = {
    "q": "LibTrack AI project by Raghav",
    "num": 5,
}

resp = requests.post(url, json=payload, headers=headers)
print("Status:", resp.status_code)
print("Body:", resp.text[:500])  # print first 500 chars
