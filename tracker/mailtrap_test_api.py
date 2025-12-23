# import mailtrap as mt
# import os 
# import requests
# from dotenv import load_dotenv
# from pathlib import Path

# # ✅ Find .env manually
# BASE_DIR = Path(__file__).resolve().parent.parent
# env_path = BASE_DIR / ".env"
# print("Loading env from:", env_path)

# load_dotenv(dotenv_path=env_path)

# API_KEY = os.getenv("MAILTRAP_ONBOARD_API_KEY")
# url = "https://bulk.api.mailtrap.io/api/send"

# payload = {
#   "from": {"email": "hello@demomailtrap.co", "name": "Mailtrap Test"},
#   "to": [{"email": "raghavdesai774@gmail.com"}],
#   "subject": "Test mail! ✅",
#   "text": "This is the first mail sent using Mailtrap's Bulk API!",
#   "category": "Integration Test"
# }

# headers = {
#   "Authorization": f"Bearer {API_KEY}",
#   "Content-Type": "application/json"
# }

# response = requests.request("POST", url, headers=headers, data=payload)

# print("response-",response)
# print("status code-",response.status_code)
# print("text-",response.text)







# import mailtrap as mt
# import os 
# import requests
# from dotenv import load_dotenv
# from pathlib import Path

# # ✅ Find .env manually
# BASE_DIR = Path(__file__).resolve().parent.parent
# env_path = BASE_DIR / ".env"
# print("Loading env from:", env_path)

# load_dotenv(dotenv_path=env_path)

# API_KEY = os.getenv("MAILTRAP_ONBOARD_API_KEY")
# if not API_KEY:
#     raise RuntimeError("MAILTRAP_API_KEY missing in .env")

# url = "https://bulk.api.mailtrap.io/api/send"

# payload = {
#   "from": {"email": "hello@demomailtrap.co", "name": "Mailtrap Test"},
#   "to": [{"email": "raghavdesai774@gmail.com"}],
#   "subject": "Test mail! ✅",
#   "text": "This is the first mail sent using Mailtrap's Bulk API!",
#   "category": "Integration Test"
# }

# headers = {
#   "Authorization": f"Bearer {API_KEY}",
#   "Content-Type": "application/json"
# }

# response = requests.request("POST", url, headers=headers, json=payload)

# print("response-",response)
# print("status code-",response.status_code)
# print("text-",response.text)


import os
import requests
from dotenv import load_dotenv

load_dotenv()

# Mailtrap bulk (Transactional) API endpoint
MAILTRAP_BULK_ENDPOINT = "https://bulk.api.mailtrap.io/api/send"

# All keys to test
MAILTRAP_KEYS = {
    "MAILTRAP_ONBOARD_API_KEY": os.getenv("MAILTRAP_ONBOARD_API_KEY"),
    "MAILTRAP_API_KEY": os.getenv("MAILTRAP_API_KEY"),
    "MAILTRAP_MAIN_KEY": os.getenv("MAILTRAP_MAIN_KEY"),
    "MAILTRAP_sandbox_API_KEY": os.getenv("MAILTRAP_sandbox_API_KEY"),
}

FROM_EMAIL = os.getenv("MAILTRAP_FROM_EMAIL", "hello@demomailtrap.co")

# Minimal payload
payload = {
    # "from": {"email": FROM_EMAIL, "name": "LibTrack AI"},
    "from": {"email": "hello@demomailtrap.co", "name": "LibTrack AI"},
    "to": [{"email": "raghavdesai774@gmail.com"}],
    "subject": "LibTrack AI Test Email - Bulk API Key Validation",
    "html": "<p>This is a test to check which API key works for production.</p>",
}

headers_template = {"Content-Type": "application/json"}

print("🔍 Testing all Mailtrap keys with the Bulk API endpoint...\n")

working_keys = []

for key_name, api_key in MAILTRAP_KEYS.items():
    if not api_key:
        print(f"⚠️  {key_name} is missing in .env\n")
        continue

    headers = headers_template | {"Authorization": f"Bearer {api_key}"}
    print(f"📡 Testing {key_name} ...")
    try:
        resp = requests.post(MAILTRAP_BULK_ENDPOINT, headers=headers, json=payload)
        print(f"➡️  Response Code: {resp.status_code}")
        print(f"📜 Response Body: {resp.text[:200]}\n")

        if 200 <= resp.status_code < 300:
            print(f"✅ SUCCESS: {key_name} works with the bulk endpoint!\n")
            working_keys.append(key_name)
        elif resp.status_code == 401:
            print(f"❌ Unauthorized: {key_name} does NOT have permission for bulk sending.\n")
        else:
            print(f"⚠️ Unexpected response: {resp.status_code} - {resp.text[:200]}\n")

    except Exception as e:
        print(f"💥 Exception testing {key_name}: {e}\n")

if working_keys:
    print("✅ Working Production Key(s):", working_keys)
else:
    print("❌ None of the keys worked. Check Mailtrap permissions for 'demomailtrap.co (Domain - Admin)' and ensure this is a Transactional project.")
