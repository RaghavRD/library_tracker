
# import sys, os
# sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# from utils.google_sheet_manager import GoogleSheetManager
# gsm = GoogleSheetManager()
# print("✅ Authenticated! Sheet title:", gsm.sheet.title)

import sys
from pathlib import Path

# Add the project root to PYTHONPATH dynamically
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT_DIR))

from tracker.utils.google_sheet_manager import GoogleSheetManager
gsm = GoogleSheetManager()
for r in gsm.read_all_registrations():
    print(r)