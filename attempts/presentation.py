from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from accounts.services import ensure_user_profile, profile_initials, profile_short_name
from interactive_templates.text import count_label
from interactive_templates.utils import is_scoring_enabled


PLAYER_UNIT_LABELS = {
    "quiz": "вопросов",
    "wheel_of_fortune": "секторов",
    "choose_a_box": "коробок",
    "matching": "пар",
    "categorize": "карточек",
    "snake": "яблок",
}

# One, few, many: «1 вопрос», «2 вопроса», «5 вопросов».
PLAYER_UNIT_FORMS = {
    "quiz": ("вопрос", "вопроса", "вопросов"),
    "wheel_of_fortune": ("сектор", "сектора", "секторов"),
    "choose_a_box": ("коробка", "коробки", "коробок"),
    "matching": ("пара", "пары", "пар"),
    "categorize": ("карточка", "карточки", "карточек"),
    "snake": ("яблоко", "яблока", "яблок"),
}

# How a run goes, told to the student on the start page.
PLAYER_HOW_TO = {
    "quiz": "Вопросы идут по одному: выберите ответ, и откроется следующий.",
    "wheel_of_fortune": "Крутите колесо: на каком секторе оно остановится, на тот вопрос и отвечаете.",
    "choose_a_box": "Открывайте коробки в любом порядке: в каждой спрятан вопрос.",
    "matching": "Подберите к каждому вопросу карточку с ответом из общего набора.",
    "categorize": "Переворачивайте карточки по одной и выбирайте правильный ответ.",
    "snake": "Ведите змейку к яблокам стрелками: каждое яблоко открывает вопрос.",
}

POINT_FORMS = ("балл", "балла", "баллов")


def _safe_avatar_url(profile: object | None) -> str:
    avatar = getattr(profile, "avatar", None)
    if not avatar or not getattr(avatar, "name", ""):
        return ""
    try:
        return avatar.url
    except ValueError:
        return ""


def _player_total_count(runtime: dict[str, Any]) -> int:
    return int(runtime.get("total_count") or 0)


def _player_answered_count(runtime: dict[str, Any]) -> int:
    return int(runtime.get("answered_count") or 0)


def _player_mode_labels(mode: str) -> tuple[str, str, str]:
    if mode == "launch":
        return ("Старт интерактива", "Готово к запуску", "Введите имя и начните прохождение в один клик.")
    if mode == "results":
        return (
            "Результаты",
            "Можно пройти ещё раз",
            "Этот результат уже сохранён. Новая попытка начнётся с первого задания.",
        )
    return ("Интерактив Quizzart", "Текущий прогресс", "Отвечайте по порядку и следите за результатом в реальном времени.")


def _participant_context(
    request: HttpRequest,
    session: object | None,
    participant_name: str,
    preview: bool = False,
) -> dict[str, str]:
    user = getattr(request, "user", None)
    if preview and user is not None and user.is_authenticated:
        # The teacher's preview: the bar shows who is looking, not a student.
        profile = ensure_user_profile(user)
        return {
            "label": "Учитель",
            "name": profile_short_name(user, profile),
            "initials": profile_initials(user, profile),
            "avatar_url": _safe_avatar_url(profile),
        }

    participant_user = getattr(session, "participant_user", None)
    if participant_user and getattr(participant_user, "is_authenticated", False):
        profile = ensure_user_profile(participant_user)
        return {
            "label": "Ученик",
            "name": participant_name or profile_short_name(participant_user, profile),
            "initials": profile_initials(participant_user, profile),
            "avatar_url": _safe_avatar_url(profile),
        }

    if participant_name:
        initials = "".join(part[:1].upper() for part in participant_name.split()[:2]) or participant_name[:1].upper()
        return {
            "label": "Ученик",
            "name": participant_name,
            "initials": initials,
            "avatar_url": "",
        }

    return {
        "label": "Гость",
        "name": "Гость",
        "initials": "Q",
        "avatar_url": "",
    }


def _shows_review(template_definition: object, config: dict[str, Any], runtime: dict[str, Any]) -> bool:
    """False when the results page shows the total only (a quiz without «Показывать результат в конце»)."""
    if "show_review" in runtime:
        return bool(runtime["show_review"])
    shows_review = getattr(template_definition, "shows_review", None)
    return bool(shows_review(config)) if callable(shows_review) else True


def _launch_facts(
    template_key: str,
    total_count: int,
    max_score: int,
    scoring_enabled: bool,
    shows_review: bool,
) -> list[dict[str, str]]:
    """What a student wants to know before starting: how long, whether points count, what comes at the end."""
    if not total_count:
        return []
    one, few, many = PLAYER_UNIT_FORMS.get(template_key, ("задание", "задания", "заданий"))
    facts = [{"key": "count", "text": count_label(total_count, one, few, many)}]
    if not scoring_enabled:
        facts.append({"key": "points", "text": "Без баллов: считаются верные ответы"})
    elif max_score:
        facts.append({"key": "points", "text": f"Максимум {count_label(max_score, *POINT_FORMS)}"})
    facts.append({"key": "end", "text": "В конце — разбор ответов" if shows_review else "В конце — только итог"})
    return facts


def build_player_shell_context(
    request: HttpRequest,
    activity: object,
    template_definition: object,
    runtime: dict[str, Any],
    *,
    session: object | None = None,
    preview: bool = False,
    mode: str = "play",
    participant_name: str = "",
) -> dict[str, Any]:
    template_key = getattr(activity, "template_key", "")
    config = getattr(activity, "config_json", {}) or {}
    total_count = _player_total_count(runtime)
    answered_count = _player_answered_count(runtime)
    remaining_count = max(total_count - answered_count, 0)
    current_score = int(getattr(session, "score", 0) or 0)
    max_score = int(getattr(session, "max_score", 0) or runtime.get("max_score") or 0)
    percent_score = int(round(float(getattr(session, "percent_score", 0) or 0))) if session else 0
    # On the results page the ring and the bar show the result, labelled as such: the run itself is over.
    if mode == "results" and session:
        progress_percent = percent_score
    else:
        progress_percent = int(round((answered_count / total_count) * 100)) if total_count else 0
    hero_eyebrow, spotlight_title, spotlight_text = _player_mode_labels(mode)
    participant = _participant_context(request, session, participant_name, preview)
    item_label = PLAYER_UNIT_LABELS.get(template_key, "элементов")
    filled_segments = max(0, min(5, round(progress_percent / 20)))
    scoring_enabled = is_scoring_enabled(config)
    shows_review = _shows_review(template_definition, config, runtime)
    # While playing, a running score would tell which answers were right when the template hides that.
    reveals_correctness = getattr(template_definition, "reveals_correctness", None)
    hides_score = mode == "play" and callable(reveals_correctness) and not reveals_correctness(config)

    summary_cards: list[dict[str, str]] = []
    fact_rows: list[dict[str, str]] = []
    launch_facts: list[dict[str, str]] = []
    footer_title = progress_heading = ""
    if mode == "launch":
        # Nothing has happened yet: no zero scores and no progress, only what the run will be like.
        launch_facts = _launch_facts(template_key, total_count, max_score, scoring_enabled, shows_review)
    elif mode == "results":
        # The one summary of the run; the board below lists the answers.
        summary_cards = [
            {"key": "result", "label": "Результат", "value": f"{percent_score}%", "suffix": "", "tone": "accent"},
            {
                "key": "score",
                "label": "Баллы" if scoring_enabled else "Верно",
                "value": str(current_score),
                "suffix": f"из {max_score}",
                "tone": "peach",
            },
            {
                "key": "answered",
                "label": "Отвечено",
                "value": str(answered_count),
                "suffix": f"из {total_count}",
                "tone": "violet",
            },
        ]
        footer_title = "Итог прохождения"
        progress_heading = f"Результат {percent_score}%"
    else:
        summary_cards = [
            {
                "key": "score",
                "label": "Очки" if scoring_enabled else "Верные ответы",
                "value": "—" if hides_score else str(current_score),
                "suffix": "",
                "tone": "accent",
            },
            {"key": "progress", "label": "Прогресс", "value": f"{progress_percent}%", "suffix": "", "tone": "peach"},
            {"key": "total", "label": item_label.capitalize(), "value": str(total_count), "suffix": "", "tone": "violet"},
        ]
        fact_rows = [
            {"key": "answered", "label": "Отвечено", "value": f"{answered_count} из {total_count}" if total_count else "0"},
            {"key": "remaining", "label": "Осталось", "value": str(remaining_count)},
            {
                "key": "max",
                "label": "Максимум" if scoring_enabled else "Всего заданий",
                "value": str(max_score) if max_score else "—",
            },
        ]
        footer_title = "Ваш прогресс"
        progress_heading = f"{progress_percent}% готово"

    return {
        "hero_eyebrow": hero_eyebrow,
        "template_title": getattr(getattr(template_definition, "metadata", None), "title", ""),
        "template_description": getattr(getattr(template_definition, "metadata", None), "description", ""),
        "how_to": PLAYER_HOW_TO.get(template_key, ""),
        "spotlight_title": spotlight_title,
        "spotlight_text": spotlight_text,
        "participant": participant,
        "progress_percent": progress_percent,
        "progress_heading": progress_heading,
        "progress_segments": [{"filled": index < filled_segments} for index in range(5)],
        "answered_count": answered_count,
        "remaining_count": remaining_count,
        "total_count": total_count,
        "item_label": item_label,
        "score": current_score,
        "max_score": max_score,
        "percent_score": percent_score,
        "scoring_enabled": scoring_enabled,
        "shows_review": shows_review,
        "summary_cards": summary_cards,
        "launch_facts": launch_facts,
        "fact_rows": fact_rows,
        "footer_title": footer_title,
        "footer_text": "Следите за ходом интерактива и возвращайтесь к экрану после каждого ответа.",
        "mode": mode,
        "is_preview": preview,
    }
