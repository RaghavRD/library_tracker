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
- PostgreSQL via Supabase in production; SQLite fallback for local development

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
- Vercel Cron — invokes a protected Django endpoint for the daily global check

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

---

## Running Locally

The same codebase runs locally and on Vercel. Which mode you get is decided
entirely by environment variables — there is no separate settings file.

| | Local | Vercel |
|---|---|---|
| Config source | `.env` file (gitignored) | Vercel env vars |
| Mode trigger | `DJANGO_ENV=local` (or unset) | `VERCEL=1` is injected automatically |
| Database | SQLite (`DATABASE_URL` blank) | Supabase Postgres via `DATABASE_URL` |
| `DEBUG` | `True` | `False` (enforced — boot fails otherwise) |
| HTTPS redirect / secure cookies / HSTS | off | on |
| File logging | `libtrack.log` | stdout only (ephemeral filesystem) |
| Static files | served by Django dev server | served by Vercel CDN |
| "Run daily check now" dashboard button | enabled | hidden (use Vercel Cron) |

`.env` never reaches Vercel — it is gitignored, so it is not in the repo that
Vercel builds. And `load_dotenv()` does **not** override real environment
variables, so on Vercel the dashboard values always win.

### First-time setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # then fill in your API keys
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://localhost:8000 — it redirects to `/libtracker/login/`.

### Switching the local database

Local defaults to SQLite. To point local dev at the live Supabase database
instead, uncomment `DATABASE_URL` in `.env` and restart the server. Everything
you do then writes to production data, so prefer SQLite for day-to-day work.

### Running the daily check locally

```bash
python manage.py run_daily_check                     # your projects
python manage.py run_daily_check --global-run        # every owner
```

To exercise the cron endpoint itself:

```bash
curl -H "Authorization: Bearer $CRON_SECRET" \
     http://localhost:8000/libtracker/internal/cron/daily-check/
```

### Email in local development

`TEST_MODE=True` writes rendered emails to `email_previews/` instead of sending
them through Mailtrap. Keep it on locally unless you are deliberately testing
delivery.

### GitHub OAuth locally

A GitHub OAuth App accepts only one callback URL, so register a second app for
development with the callback
`http://localhost:8000/accounts/github/login/callback/`, and put its client ID
and secret in `.env`. Leaving `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` blank
simply hides the GitHub sign-in button.

## Database Configuration

For production, set `DATABASE_URL` to the Supabase **Transaction pooler** URI
(port `6543`). Keep this value in `.env` locally and in Vercel environment
variables; never commit it to Git. The application falls back to local SQLite
when `DATABASE_URL` is absent.

```env
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-<region>.pooler.supabase.com:6543/postgres
```

## Logging on Vercel

Vercel deployments write logs to standard output and error, which are available
in the Vercel dashboard. Local file logging is enabled by default; set
`ENABLE_FILE_LOGGING=False` to disable local `libtrack.log` files.

## Daily Check Schedule

Vercel Cron invokes `/libtracker/internal/cron/daily-check/` daily at 03:30 UTC
(approximately 09:00 India time). Set a random `CRON_SECRET` in Vercel and use
the same value only for local cron-route testing. The endpoint rejects requests
without `Authorization: Bearer <CRON_SECRET>`.

## Vercel Environment Variables

Set these values in Vercel Project Settings before the first production deploy:

```env
DJANGO_ENV=production
SECRET_KEY=<generate-a-new-random-value>
DEBUG=False
DATABASE_URL=<Supabase-transaction-pooler-URI>
ALLOWED_HOSTS=<your-vercel-or-custom-domain>
CSRF_TRUSTED_ORIGINS=https://<your-vercel-or-custom-domain>
CRON_SECRET=<generate-a-separate-random-value>
```

Add the Groq, Serper, Mailtrap, and GitHub OAuth variables from your local
`.env` before enabling the production daily check. Never commit any secret.

## Deploying on Vercel

Vercel automatically detects this Django application from `manage.py`; no
separate Python entrypoint or custom build command is required. Keep the Vercel
project root directory at the repository root and deploy the
`vercel-ready-libtrack` branch as the production branch. Static files are served
by Vercel's CDN and the Supabase schema must be migrated before deployment.

---

## Author

Built by **Raghav Desai**
