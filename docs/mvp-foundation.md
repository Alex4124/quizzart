# Quizzart MVP Foundation

## 1. MVP scope

- Teachers can register, log in, create activities, edit content, preview and publish by share link.
- Students can open a public link, run an activity, submit answers and receive a result screen.
- The system stores sessions and answers, then exposes basic analytics to the teacher.
- All five templates publish and launch in this phase.
- `choose_a_box` and `quiz` remain the primary reference implementations for richer end-to-end behavior.
- The rest reuse the same architecture and common question bank contract.

## 2. Architecture

- One Django monolith with four apps:
  - `accounts`
  - `activities`
  - `attempts`
  - `dashboard`
- `interactive_templates` is a plain Python package, not a Django app.
- Storage is relational:
  - `Activity` stores the author, template key and serialized config
  - `ShareLink` stores the public URL handle
  - `ActivitySession` stores one student run
  - `ActivityAnswer` stores per-item answers
- Server-rendered pages drive the MVP:
  - Django templates for dashboard, editor and player
  - minimal CSS
  - no frontend framework

## 3. Domain entities

- `User`: built-in Django auth user for teachers
- `Activity`: teacher-owned interactive draft/publication unit
- `ShareLink`: public access handle for a published activity
- `ActivitySession`: one student run with aggregate score and runtime state
- `ActivityAnswer`: one persisted answer per item within a session

## 4. Template system

Unified template contract:

- `metadata`
- `default_config()`
- `build_editor_initial()`
- `build_config()`
- `validate_config()`
- `build_runtime_data()`
- `get_max_score()`
- `evaluate_submission()`

Shared authoring format:

- one question bank consumed by every template
- each row is `Prompt | *Correct answer | Wrong answer 1 | Wrong answer 2 | optional points`
- template definitions map the same items into boxes, quiz questions, wheel sectors, matching pairs or category assignments

Rationale:

- Python-first and explicit
- keeps editor schema and runtime logic together
- avoids hardcoded per-template branches in models
- makes future templates additive via registry registration

## 5. Repository structure

```text
quizzart/
|-- accounts/
|-- activities/
|-- attempts/
|-- config/
|-- dashboard/
|-- docs/
|-- interactive_templates/
|   `-- definitions/
|-- static/
|   `-- css/
|-- templates/
|   |-- accounts/
|   |-- activities/
|   |-- dashboard/
|   |-- player/
|   `-- registration/
|-- AGENTS.md
|-- README.md
|-- manage.py
`-- requirements.txt
```

## 6. Delivery phases

1. Bootstrap the monolith, settings, apps and database config
2. Add domain models, migrations and admin
3. Add template registry and five registered definitions
4. Build dashboard, editor and public player shells
5. Finish `choose_a_box` and `quiz` end-to-end
6. Make all registered templates publishable and launchable from the same question bank
7. Add README, AGENTS guide and smoke tests

## 7. First commit content

- Django project bootstrap
- app skeletons
- settings with PostgreSQL support
- core models and initial migrations
- template registry and five registered templates
- baseline dashboard/editor/player templates
- README and AGENTS guide

## 8. Files created in this stage

- Django settings, urls and app wiring
- domain models for activities and attempts
- template engine package and registered definitions
- editor, dashboard and player templates
- project README
- `AGENTS.md`
- architecture note in `docs/mvp-foundation.md`
- smoke tests
