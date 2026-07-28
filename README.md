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

## Database Configuration

For production, set `DATABASE_URL` to the Supabase **Transaction pooler** URI
(port `6543`). Keep this value in `.env` locally and in Vercel environment
variables; never commit it to Git. The application falls back to local SQLite
when `DATABASE_URL` is absent.

```env
DATABASE_URL=postgresql://postgres.<project-ref>:<password>@aws-<region>.pooler.supabase.com:6543/postgres
```

---

## Author

Built by **Raghav Desai**
