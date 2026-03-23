# Quizzart

Quizzart is a Python-first MVP for building classroom interactives in a single Django monolith.

## Current MVP

- Teacher auth, dashboard and editor
- Activity drafts, publish-by-link and duplication
- Public player with saved results
- Basic analytics by activity
- Registered templates:
  - `choose_a_box`
  - `quiz`
  - `wheel_of_fortune`
  - `matching`
  - `categorize`
- End-to-end playable templates:
  - `choose_a_box`
  - `quiz`

## Stack

- Python 3.12+
- Django 5.2
- PostgreSQL via environment variables
- SQLite fallback for zero-friction local bootstrap

## Quick start

### 1. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 3. Configure the database

SQLite fallback works out of the box. For PostgreSQL, set:

```powershell
$env:QUIZZART_DB_NAME="quizzart"
$env:QUIZZART_DB_USER="postgres"
$env:QUIZZART_DB_PASSWORD="postgres"
$env:QUIZZART_DB_HOST="127.0.0.1"
$env:QUIZZART_DB_PORT="5432"
```

Optional settings:

```powershell
$env:QUIZZART_SECRET_KEY="change-me"
$env:QUIZZART_DEBUG="true"
$env:QUIZZART_ALLOWED_HOSTS="127.0.0.1,localhost"
$env:QUIZZART_TIME_ZONE="Europe/Moscow"
```

### 4. Apply migrations and create a user

```powershell
python manage.py migrate
python manage.py createsuperuser
```

### 5. Run the project

```powershell
python manage.py runserver
```

Open:

- Landing page: `http://127.0.0.1:8000/`
- Admin: `http://127.0.0.1:8000/admin/`
- Dashboard: `http://127.0.0.1:8000/dashboard/`

## Project notes

- The template system is code-registered and Python-driven.
- Each template definition owns:
  - metadata
  - editor form
  - config builder
  - validator
  - runtime data builder
  - result calculator / submission evaluator
- `choose_a_box` supports incremental box answering.
- `quiz` supports single-answer quiz submission and end-of-run scoring.

## Tests

```powershell
python manage.py test
```
