import os
import sys
import django

# Add the project root directory to the Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Set up Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'libtrack_ai.settings')
django.setup()

# Now we can import from the tracker app
from tracker.utils.send_mail import send_update_email

# Test mail works
ok, info = send_update_email(
    mailtrap_api_key=None,
    project_name="LibTrack AI Test Project",
    recipients="raghavdesai549@gmail.com",
    library="pandas",
    version="2.2.3",
    category="major",
    summary="Big performance & bug fixes release.",
    source="https://pandas.pydata.org/docs/whatsnew/index.html",
    from_email=None,
)

print("status:", ok)
print("INFO:", info)
