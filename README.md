# LibTrack AI

**AI-powered dependency version tracker for software projects.**  
Register your projects, define your tech stack, and get automatically notified whenever a new version of a library, language, or tool you depend on is released — with AI-predicted future releases included.

---

## What it does

Most teams find out about dependency updates too late — during a security audit, a failing build, or a colleague's offhand comment. LibTrack AI fixes that by:

- Continuously checking official registries (PyPI, npm, RubyGems, Cargo, GitHub) for the latest stable versions of every dependency in your stack
- Sending email notifications to your team when updates are available, filtered by type (major / minor / future)
- Using an LLM (Groq) backed by web search (Serper) to **predict upcoming releases** before they are officially published, with a confidence score per prediction
- Giving you a live dashboard with a health score, update breakdown charts, and a future roadmap view

---

## Features

| Feature | Description |
|---|---|
| **Project Registry** | Register any project with team names, emails, and a full technology stack (languages, libraries, tools, modules) |
| **Multi-Registry Detection** | Fetches latest stable versions from PyPI, npm, RubyGems, Cargo, and GitHub Releases |
| **AI Fallback** | If an official API fails, Serper (Google search) + Groq LLM extracts the correct version from the web |
| **Future Version Prediction** | Groq analyses release cadence and public signals to predict upcoming releases with confidence scores |
| **Smart Notifications** | Email alerts via Mailtrap — configurable per project (major only, minor, future, or all) |
| **Notification Pause** | Temporarily silence notifications for a project without removing it |
| **Confidence Threshold** | Only receive future-update notifications above a user-defined confidence level (0–100%) |
| **Health Score** | Dashboard metric showing what percentage of your tracked libraries are up-to-date |
| **Dark / Light Theme** | GitHub-dark design system with a persistent theme toggle |

---

## Tech Stack

**Backend**
- [Django 5.2](https://www.djangoproject.com/) — web framework
- Python 3.14
- SQLite — default database (drop-in replaceable with PostgreSQL)

**AI / Data**
- [Groq API](https://console.groq.com/) — LLM inference for version analysis and future release prediction
- [Serper API](https://serper.dev/) — Google Search API used as a version-detection fallback and for future release signals

**Notifications**
- [Mailtrap](https://mailtrap.io/) — transactional email (bulk API)

**Frontend**
- [Bootstrap 5.3](https://getbootstrap.com/) — grid and utility classes
- Custom GitHub-dark design system (`style.css`) — full dark/light token palette, overrides all Bootstrap visuals
- [Chart.js](https://www.chartjs.org/) — dashboard bar and doughnut charts
- [Bootstrap Icons](https://icons.getbootstrap.com/)

**Scheduler**
- `schedule` library — powers the daily check loop inside the `run_daily_check` management command

---

## How the Daily Check Works

```
python manage.py run_daily_check
        │
        ▼
1. LibrarySyncService     — link all StackComponents to central Library records
        │
        ▼
2. VersionFetchService    — query official registries for latest stable versions
        │                   fallback: Serper search + Groq LLM extraction
        ▼
3. FutureUpdateService    — predict upcoming releases via Groq analysis
        │                   stores confidence score per prediction
        ▼
4. NotificationService    — send emails to project teams via Mailtrap
                            respects per-project type filter + confidence threshold
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- API keys for [Groq](https://console.groq.com/), [Serper](https://serper.dev/), and [Mailtrap](https://mailtrap.io/) (all have free tiers)

### 1. Clone and install

```bash
git clone https://github.com/your-username/LibTrack-AI.git
cd LibTrack-AI
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
# Django
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
TIME_ZONE=Asia/Kolkata

# API Keys
GROQ_API_KEY=your-groq-api-key
SERPER_API_KEY=your-serper-api-key

# Email (Mailtrap)
MAILTRAP_API_KEY=your-mailtrap-api-key
MAILTRAP_FROM_EMAIL=noreply@yourdomain.com

# Feature flags (optional — defaults shown)
LIBTRACK_ENABLE_EMAIL_NOTIFICATIONS=True
LIBTRACK_USE_OFFICIAL_APIS=True
LIBTRACK_FETCH_DEBUG_MODE=False
LIBTRACK_MIN_FUTURE_CONFIDENCE=40
LIBTRACK_MAX_FUTURE_CONFIDENCE=95
LIBTRACK_API_RATE_LIMIT_SECONDS=1.5
LIBTRACK_DEDUP_WINDOW_HOURS=24
LIBTRACK_EMAIL_BATCH_SIZE=10
LIBTRACK_MAX_NOTIFICATION_RETRIES=3
LIBTRACK_LOG_LEVEL=INFO
```

### 3. Run migrations and create a user

```bash
python manage.py migrate
python manage.py createsuperuser
```

### 4. (Optional) Seed demo data

```bash
python manage.py seed_test_data
```

### 5. Start the development server

```bash
python manage.py runserver
```

Open [http://127.0.0.1:8000/libtracker/login/](http://127.0.0.1:8000/libtracker/login/)

---

## Running the Daily Check

Run project:

```bash
python manage.py runserver
```

Clear cache:

```bash
python manage.py clear_cache
```

One-off run (useful for testing):

```bash
python manage.py run_daily_check --auto --time 22:22
```

Continuous scheduler (runs every 24 hours):

```bash
python manage.py run_daily_check
```

In production, run this as a background service via systemd, supervisor, or a cron job.

---

## Useful Management Commands

| Command | Purpose |
|---|---|
| `run_daily_check` | Full sync → fetch → predict → notify pipeline |
| `clear_cache` | Wipe UpdateCache and FutureUpdateCache tables |
| `seed_test_data` | Populate database with sample projects and stack data |
| `test_email` | Send a test email to verify Mailtrap configuration |
| `verify_adapters` | Check that all registry adapters are reachable |

---

## Supported Registries

| Registry | Ecosystem |
|---|---|
| PyPI | Python packages |
| npm | JavaScript / Node.js |
| RubyGems | Ruby gems |
| Cargo (crates.io) | Rust crates |
| GitHub Releases | Any library with a public GitHub repo |

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes | — | Django secret key |
| `DEBUG` | No | `False` | Enable Django debug mode |
| `ALLOWED_HOSTS` | No | `127.0.0.1` | Comma-separated allowed hosts |
| `TIME_ZONE` | No | `UTC` | Django timezone |
| `GROQ_API_KEY` | Yes | — | Groq LLM API key |
| `SERPER_API_KEY` | Yes | — | Serper Google Search API key |
| `MAILTRAP_API_KEY` | Yes* | — | Mailtrap bulk API key |
| `MAILTRAP_FROM_EMAIL` | Yes* | — | Sender email address |
| `LIBTRACK_ENABLE_EMAIL_NOTIFICATIONS` | No | `True` | Toggle email dispatch globally |
| `LIBTRACK_USE_OFFICIAL_APIS` | No | `True` | Use official registry APIs first |
| `LIBTRACK_MIN_FUTURE_CONFIDENCE` | No | `40` | Minimum confidence % to store a future prediction |
| `LIBTRACK_MAX_FUTURE_CONFIDENCE` | No | `95` | Cap on AI-reported confidence scores |
| `LIBTRACK_FETCH_DEBUG_MODE` | No | `False` | Log raw API responses |
| `LIBTRACK_API_RATE_LIMIT_SECONDS` | No | `1.5` | Delay between registry API calls |
| `LIBTRACK_DEDUP_WINDOW_HOURS` | No | `24` | Hours before re-sending the same notification |

*Required only when `LIBTRACK_ENABLE_EMAIL_NOTIFICATIONS=True`

---

## Running Tests

```bash
pytest --cov=tracker
```

---

## Contributing

1. Fork the repo and create a feature branch: `git checkout -b feat/your-feature`
2. Make your changes and add tests where relevant
3. Run `pytest` to confirm nothing is broken
4. Open a Pull Request with a clear description

---

## Author

Built by **Raghav Desai**
