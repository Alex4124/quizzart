# Quizzart Agent Guide

## Product direction

- Build a practical MVP for teachers to create, publish and review interactive learning activities.
- Keep the project Python-first and monolithic.
- Optimize for shipping speed, maintainability and template extensibility.

## Primary stack

- Python 3.12+
- Django 5.x
- PostgreSQL in real environments
- Django templates for server-rendered pages
- Minimal JavaScript only when it removes real friction

## Architectural boundaries

- `accounts`: teacher registration and auth views
- `activities`: activity domain, editor, publishing, share links
- `attempts`: student sessions, answers, results
- `dashboard`: landing page and analytics UI
- `interactive_templates`: Python registry and template definitions

## Template system contract

Every activity template should be represented by a definition class in `interactive_templates/definitions/`.

Each definition is responsible for:

- `metadata`
- `default_config()`
- `build_editor_initial()`
- `build_config()`
- `validate_config()`
- `build_runtime_data()`
- `get_max_score()`
- `evaluate_submission()`

Rules:

- Prefer Django forms for editor schema in MVP.
- Keep configs serializable into `Activity.config_json`.
- Do not special-case templates in models; special behavior belongs in the definition.
- New templates should register through `register_all_templates()`.

## MVP priorities

- Keep `choose_a_box` and `quiz` fully working end-to-end.
- Other templates may stay registered-but-not-playable until their runtime is implemented.
- Avoid overengineering editor UX before the player flow and result persistence are stable.

## Coding rules

- Prefer simple function-based views unless a class-based view is clearly better.
- Reuse Django auth/admin/forms/ORM features before adding custom abstractions.
- Add comments only when the logic is not immediately obvious.
- Keep user-facing flows mobile-safe and server-rendered by default.
- Do not add new dependencies unless they save real implementation time.

## Testing expectations

- Add or update tests when changing domain logic, template evaluation or publish/play flows.
- At minimum, keep smoke coverage for template registration and the two playable templates.
