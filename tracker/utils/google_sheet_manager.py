import os
import json
import gspread
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
from google.oauth2.service_account import Credentials
from gspread.exceptions import WorksheetNotFound, APIError

BASE_DIR = Path(__file__).resolve().parent.parent

# ✅ Load .env safely (works even if in different location)
env_path = find_dotenv() or (BASE_DIR / ".env")
if not load_dotenv(dotenv_path=env_path):
    raise RuntimeError(f"Failed to load environment file: {env_path}")

SCOPE = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
HEADERS = [
    "project_name", "developer_names", "developer_emails",
    "language_used", "language_version", "libraries",
    "library_versions", "notification_type",
]

class GoogleSheetManager:
    def __init__(self, tab_name: str = "Registrations"):
        sheet_id = os.getenv("GOOGLE_SHEET_ID")
        if not sheet_id:
            raise RuntimeError("GOOGLE_SHEET_ID missing in .env")

        sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH")
        sa_inline = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_INLINE")

        creds = None
        if sa_path and os.path.exists(sa_path):
            creds = Credentials.from_service_account_file(sa_path, scopes=SCOPE)
        elif sa_inline:
            try:
                creds_dict = json.loads(sa_inline)
                creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPE)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"Invalid GOOGLE_SERVICE_ACCOUNT_JSON_INLINE: {e}")
        else:
            raise RuntimeError("Missing service account credentials (path or inline JSON).")

        client = gspread.authorize(creds)
        self.sheet = client.open_by_key(sheet_id)

        try:
            self.ws = self.sheet.worksheet(tab_name)
        except WorksheetNotFound:
            self.ws = self.sheet.add_worksheet(title=tab_name, rows="1000", cols="20")
            self.ws.append_row(HEADERS)

    def append_registration(self, data: dict) -> None:
        row = [data.get(h, "") for h in HEADERS]
        try:
            self.ws.append_row(row, value_input_option="RAW")
        except APIError as e:
            raise RuntimeError(f"Google Sheets API error during append: {e}")

    def read_all_registrations(self) -> list[dict]:
        try:
            values = self.ws.get_all_records()
        except APIError as e:
            raise RuntimeError(f"Google Sheets API error during read: {e}")

        normalized = [{k: v.get(k, "") for k in HEADERS} for v in values]
        return normalized



# import os
# import json
# import gspread
# from pathlib import Path
# from dotenv import load_dotenv, find_dotenv
# from oauth2client.service_account import ServiceAccountCredentials

# # ✅ Locate the .env file one level above 'tracker/'
# BASE_DIR = Path(__file__).resolve().parent.parent
# env_path = BASE_DIR / ".env"

# # Load .env explicitly
# load_dotenv(dotenv_path=env_path)

# SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# HEADERS = [
#     "project_name",
#     "developer_names",
#     "developer_emails",
#     "language_used",
#     "language_version",
#     "libraries",
#     "library_versions",
#     "notification_type",
# ]

# class GoogleSheetManager:
#     def __init__(self):
#         sheet_id = os.getenv("GOOGLE_SHEET_ID")
#         if not sheet_id:
#             raise RuntimeError("GOOGLE_SHEET_ID missing in .env")

#         sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH")
#         sa_inline = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_INLINE")

#         if sa_path and os.path.exists(sa_path):
#             creds = ServiceAccountCredentials.from_json_keyfile_name(sa_path, SCOPE)
#         elif sa_inline:
#             try:
#                 data = json.loads(sa_inline)
#             except json.JSONDecodeError as e:
#                 raise RuntimeError(f"Invalid GOOGLE_SERVICE_ACCOUNT_JSON_INLINE format: {e}")
#             creds = ServiceAccountCredentials.from_json_keyfile_dict(data, SCOPE)
#         else:
#             raise RuntimeError("Service Account JSON not provided. Set GOOGLE_SERVICE_ACCOUNT_JSON_PATH or GOOGLE_SERVICE_ACCOUNT_JSON_INLINE.")

#         client = gspread.authorize(creds)
#         self.sheet = client.open_by_key(sheet_id)
#         # Two tabs: Registrations, Logs (optional)
#         try:
#             self.ws = self.sheet.worksheet("Registrations")
#         except gspread.WorksheetNotFound:
#             self.ws = self.sheet.add_worksheet(title="Registrations", rows="1000", cols="20")
#             self.ws.append_row(HEADERS)

#     def append_registration(self, data: dict):
#         row = [data.get(h, "") for h in HEADERS]
#         self.ws.append_row(row, value_input_option="RAW")

#     def read_all_registrations(self) -> list[dict]:
#         values = self.ws.get_all_records()
#         # Normalize keys to our HEADERS set (gspread returns headers as is)
#         normalized = []
#         for v in values:
#             item = {k: v.get(k, "") for k in HEADERS}
#             normalized.append(item)
#         return normalized


