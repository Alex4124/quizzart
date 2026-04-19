from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from accounts.services import ensure_user_profile, profile_initials, profile_short_name


PLAYER_UNIT_LABELS = {
    "quiz": "вопросов",
    "wheel_of_fortune": "секторов",
    "choose_a_box": "коробок",
    "matching": "пар",
    "categorize": "карточек",
    "snake": "яблок",
}


def _safe_avatar_url(profile: object | None) -> str:
    avatar = getattr(profile, "avatar", None)
    if not avatar or not getattr(avatar, "name", ""):
        return ""
    try:
        return avatar.url
    except ValueError:
        return ""


def _player_total_count(template_key: str, runtime: dict[str, Any]) -> int:
    if template_key == "quiz":
        return len(runtime.get("questions", []))
    if template_key == "wheel_of_fortune":
        return int(runtime.get("total_items") or len(runtime.get("sectors", [])))
    if template_key == "choose_a_box":
        return int(runtime.get("total_boxes") or 0)
    if template_key == "matching":
        return len(runtime.get("rows", []))
    if template_key == "categorize":
        return len(runtime.get("cards", []))
    if template_key == "snake":
        return int(runtime.get("total_items") or len(runtime.get("apples", [])))
    return len(runtime.get("review_items", []))


def _player_answered_count(template_key: str, runtime: dict[str, Any], session: object | None) -> int:
    if template_key in {"wheel_of_fortune", "choose_a_box", "snake"}:
        return int(runtime.get("answered_count") or 0)
    if session is None:
        return 0
    answers = getattr(session, "answers", None)
    return answers.count() if hasattr(answers, "count") else 0


def _player_mode_labels(mode: str) -> tuple[str, str, str]:
    if mode == "launch":
        return ("Старт интерактива", "Готово к запуску", "Введите имя и начните прохождение в один клик.")
    if mode == "results":
        return ("Результаты", "Прохождение завершено", "Разберите ответы и при необходимости запустите интерактив заново.")
    return ("Интерактив Quizzart", "Текущий прогресс", "Отвечайте по порядку и следите за очками в реальном времени.")


def _participant_context(
    request: HttpRequest,
    session: object | None,
    participant_name: str,
) -> dict[str, str]:
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
    total_count = _player_total_count(template_key, runtime)
    answered_count = _player_answered_count(template_key, runtime, session)
    remaining_count = max(total_count - answered_count, 0)
    current_score = int(getattr(session, "score", 0) or 0)
    max_score = int(getattr(session, "max_score", 0) or runtime.get("max_score") or 0)
    percent_score = int(round(float(getattr(session, "percent_score", 0) or 0))) if session else 0
    progress_percent = (
        percent_score
        if mode == "results" and session
        else int(round((answered_count / total_count) * 100))
        if total_count
        else 0
    )
    hero_eyebrow, spotlight_title, spotlight_text = _player_mode_labels(mode)
    participant = _participant_context(request, session, participant_name)
    item_label = PLAYER_UNIT_LABELS.get(template_key, "элементов")
    filled_segments = max(0, min(5, round(progress_percent / 20)))

    if mode == "launch":
        footer_text = "Сначала запустите интерактив, а затем ответы и баллы появятся здесь."
    elif mode == "results":
        footer_text = "Баллы, процент и ответы сохранены для этого прохождения."
    else:
        footer_text = "Следите за ходом интерактива и возвращайтесь к экрану после каждого ответа."

    return {
        "hero_eyebrow": hero_eyebrow,
        "template_title": getattr(getattr(template_definition, "metadata", None), "title", ""),
        "template_description": getattr(getattr(template_definition, "metadata", None), "description", ""),
        "spotlight_title": spotlight_title,
        "spotlight_text": spotlight_text,
        "participant": participant,
        "progress_percent": progress_percent,
        "progress_segments": [{"filled": index < filled_segments} for index in range(5)],
        "answered_count": answered_count,
        "remaining_count": remaining_count,
        "total_count": total_count,
        "item_label": item_label,
        "score": current_score,
        "max_score": max_score,
        "summary_cards": [
            {"key": "score", "label": "Очки", "value": str(current_score), "tone": "accent"},
            {"key": "progress", "label": "Прогресс", "value": f"{progress_percent}%", "tone": "peach"},
            {"key": "total", "label": item_label.capitalize(), "value": str(total_count), "tone": "violet"},
        ],
        "fact_rows": [
            {"key": "answered", "label": "Отвечено", "value": f"{answered_count} из {total_count}" if total_count else "0"},
            {"key": "remaining", "label": "Осталось", "value": str(remaining_count)},
            {"key": "max", "label": "Максимум", "value": str(max_score) if max_score else "—"},
        ],
        "footer_title": "Ваш прогресс" if mode != "results" else "Итог прохождения",
        "footer_text": footer_text,
        "mode": mode,
        "is_preview": preview,
    }
