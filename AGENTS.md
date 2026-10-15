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

Question bank templates inherit `QuestionBankTemplateDefinition` (`interactive_templates/base.py`), which checks answers on the server one at a time. Its hooks:

- `check_answer()` / `resolve_choice()` / `answers_match()`: is the posted choice an option, and is it right
- `build_answer_feedback()`: what the page may learn about a saved answer (`submitted`, `is_correct`, `correct_option`, `score_awarded`), governed by `reveals_correct_option()` / `reveals_correctness()`
- `build_item_states()`: per-item render data with no answer key; answered items carry their feedback
- `score_answers()` / `is_complete()`: recomputed from saved answers with the current points and questions
- `handle_custom_action()`, `answer_item_key()`, `after_answer_state()`: template-specific actions (open a box, spin the wheel)
- `build_results_data()`: the review for the results page; `shows_review()` (quiz can hide it), `review_items_in_order()` (match the order the student saw) and `review_item_label` («Коробка», «Сектор»…)
- `evaluate_preview_action()`: the teacher's preview, nothing saved
- `legacy_bulk_actions`: whole-run submissions from pages opened before per-answer checking; keep them until no old page can still be open

Rules:

- Prefer Django forms for editor schema in MVP.
- Prefer the shared question bank input model first: `prompt + options + correct marker + optional points`.
- Keep configs serializable into `Activity.config_json`.
- Do not special-case templates in models; special behavior belongs in the definition.
- New templates should register through `register_all_templates()`.
- Never put the answer key into a player page: no correct option, `is_correct` flag or authoring-order id before the item is answered. Shuffle options with a per-session seed.
- Each answer is a real form (`action`, `item_key`, `answer`) so the page works without JavaScript; `static/js/player/core.js` (`submitAction`, `applyChoiceFeedback`, `finishIfComplete`) turns it into a fetch.
- Question ids are stable (`assign_item_ids` in `interactive_templates/utils.py`): saved answers and analytics key on them.

## MVP priorities

- Keep all registered templates publishable and launchable.
- Preserve the shared authoring contract unless there is a strong product reason to split it.
- Avoid overengineering editor UX before the player flow and result persistence are stable.

## Coding rules

- Prefer simple function-based views unless a class-based view is clearly better.
- Reuse Django auth/admin/forms/ORM features before adding custom abstractions.
- Add comments only when the logic is not immediately obvious.
- Keep user-facing flows mobile-safe and server-rendered by default.
- Do not add new dependencies unless they save real implementation time.

## Testing expectations

- Add or update tests when changing domain logic, template evaluation or publish/play flows.
- Every player keeps a no-leak test (`assert_no_answer_key` in `attempts/test_answers.py`) for play and preview pages, for each reveal setting.
- At minimum, keep smoke coverage for template registration and every playable template.
