from __future__ import annotations

from datetime import timedelta

from django.db.models import Avg, Count, Max, Prefetch, Q
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.decorators import teacher_required
from accounts.services import ensure_user_profile, profile_initials, profile_short_name, user_home_url
from activities.models import Activity, ShareLink
from attempts.models import ActivityAnswer, ActivitySession
from interactive_templates.registry import registry
from interactive_templates.text import count_label as _count_label
from interactive_templates.text import plural_form
from interactive_templates.utils import normalize_question_bank


LANDING_FEATURES = [
    {
        "icon": "bank",
        "title": "Общий банк вопросов",
        "description": (
            "Собирайте задания один раз и быстро перекладывайте их между викториной, "
            "змейкой, колесом фортуны и другими шаблонами."
        ),
    },
    {
        "icon": "share",
        "title": "Публикация по ссылке",
        "description": (
            "После настройки интерактив можно сразу открыть классу: без установки, "
            "без отдельных приложений и без ручной раздачи файлов."
        ),
    },
    {
        "icon": "analytics",
        "title": "Аналитика по прохождениям",
        "description": (
            "Сохраняйте результаты, отслеживайте завершения и смотрите средний процент "
            "успешности по каждому сценарию."
        ),
    },
]

LANDING_TEMPLATE_CARDS = [
    {
        "key": "quiz",
        "eyebrow": "Проверка знаний",
        "title": "Викторина",
        "description": "Пошаговая проверка знаний с одним правильным ответом и понятным итоговым экраном.",
        "accent_class": "landing-template-card-violet",
    },
    {
        "key": "wheel_of_fortune",
        "eyebrow": "Игра на удачу",
        "title": "Колесо фортуны",
        "description": "Вращаете колесо, получаете случайный вопрос и держите внимание класса в игровом темпе.",
        "accent_class": "landing-template-card-rose",
    },
    {
        "key": "choose_a_box",
        "eyebrow": "Сюрприз",
        "title": "Выбери коробку",
        "description": "Открывайте ячейки по одной: внутри вопросы, баллы и эффект сюрприза для каждого хода.",
        "accent_class": "landing-template-card-apricot",
    },
    {
        "key": "matching",
        "eyebrow": "Пары",
        "title": "Сопоставление",
        "description": "Соединяйте понятия и ответы по одному, чтобы тренировать точность и держать темп урока.",
        "accent_class": "landing-template-card-sky",
    },
    {
        "key": "categorize",
        "eyebrow": "Повторение",
        "title": "Карточки",
        "description": "Переворачивайте карточки по одной и повторяйте термины, факты и короткие определения.",
        "accent_class": "landing-template-card-lilac",
    },
    {
        "key": "snake",
        "eyebrow": "Аркада",
        "title": "Змейка",
        "description": "Двигайтесь по полю, собирайте вопросы и удерживайте вовлечённость через механику игры.",
        "accent_class": "landing-template-card-mint",
    },
]

LANDING_SHOWCASES = [
    {
        "eyebrow": "Быстрый старт",
        "title": "Удобно учителю:",
        "accent": "быстро собирается под урок.",
        "description": (
            "Один редактор для всех форматов, публикация по ссылке и результаты каждого ученика "
            "сразу после прохождения."
        ),
        "bullets": [
            "Единый поток: создать, опубликовать и открыть ученикам по ссылке.",
            "Минимум ручной настройки и переиспользуемый банк вопросов.",
            "Работает в любом браузере: на компьютере, планшете и телефоне.",
        ],
        "image": "img/landing-teacher-photo.webp",
        "image_alt": "Учитель за ноутбуком на фоне панели с аналитикой.",
        "frame_class": "landing-showcase__frame-photo",
        "image_class": "landing-showcase__image-cover landing-showcase__image-cover-teacher",
    },
    {
        "eyebrow": "Игровая подача",
        "title": "Интересно ученикам:",
        "accent": "движение через игру.",
        "description": (
            "Когда нужно поднять вовлечённость, Quizzart переключается на игровые форматы, "
            "но оставляет проверку ответов и результаты в одной системе."
        ),
        "bullets": [
            "Колесо, змейка и карточные сценарии для живого темпа урока.",
            "Подходит для планшета, ноутбука и обычного браузера на телефоне.",
            "После игры остаются завершения, баллы и средний процент по активности.",
        ],
        "image": "img/landing-students-photo.webp",
        "image_alt": "Двое учеников работают за ноутбуком и обсуждают ответы.",
        "frame_class": "landing-showcase__frame-photo",
        "image_class": "landing-showcase__image-cover landing-showcase__image-cover-students",
    },
]

DASHBOARD_COVER_VARIANTS = {
    "quiz": "nebula",
    "wheel_of_fortune": "orbit",
    "matching": "grid",
    "snake": "snake",
    "categorize": "stack",
    "choose_a_box": "vault",
}


def _dashboard_template_title(template_key: str) -> str:
    try:
        return registry.get(template_key).metadata.title
    except KeyError:
        return template_key.replace("_", " ").title()


def _dashboard_cover_variant(template_key: str) -> str:
    return DASHBOARD_COVER_VARIANTS.get(template_key, "default")


def _build_activity_card(activity: Activity, request) -> dict:
    active_share_links = getattr(activity, "dashboard_active_share_links", [])
    share_link = active_share_links[0] if active_share_links else None
    template_title = _dashboard_template_title(activity.template_key)
    question_count = len(normalize_question_bank(activity.config_json))
    # Share links stay active after unpublishing, but the player answers 404 for drafts,
    # so a draft card offers no link to copy.
    share_url = (
        request.build_absolute_uri(share_link.get_absolute_url())
        if share_link and activity.is_published
        else ""
    )

    return {
        "id": activity.pk,
        "title": activity.title,
        "description": activity.description,
        "template_key": activity.template_key,
        "template_title": template_title,
        "status": activity.status,
        "status_display": activity.get_status_display(),
        "created_at": activity.created_at,
        "updated_at": activity.updated_at,
        "updated_label": "Обновлено",
        "published_at": activity.published_at,
        "question_count": question_count,
        "question_count_label": _count_label(question_count, "вопрос", "вопроса", "вопросов"),
        "cover_variant": _dashboard_cover_variant(activity.template_key),
        "is_published": activity.is_published,
        "edit_url": activity.get_absolute_url(),
        "preview_url": activity.get_preview_url(),
        "analytics_url": reverse("dashboard:analytics", kwargs={"pk": activity.pk}),
        "share_url": share_url,
    }


def _matches_dashboard_query(activity_card: dict, query: str) -> bool:
    haystack = " ".join(
        part
        for part in (
            activity_card["title"],
            activity_card["description"],
            activity_card["template_key"],
            activity_card["template_title"],
        )
        if part
    ).lower()
    return query.lower() in haystack


def _build_recent_events(activity_cards: list[dict]) -> list[dict]:
    activity_ids = [activity_card["id"] for activity_card in activity_cards]
    if not activity_ids:
        return []

    activity_lookup = {activity_card["id"]: activity_card for activity_card in activity_cards}
    recent_sessions = list(
        ActivitySession.objects.filter(activity_id__in=activity_ids)
        .select_related("activity")
        .annotate(feed_at=Coalesce("completed_at", "started_at"))
        .order_by("-feed_at")[:12]
    )

    events: list[dict] = []
    for session in recent_sessions:
        activity_card = activity_lookup.get(session.activity_id)
        if not activity_card:
            continue

        participant = session.participant_name or "Анонимный ученик"
        if session.status == ActivitySession.Status.COMPLETED and session.completed_at:
            events.append(
                {
                    "kind": "completed",
                    "title": "Завершено прохождение",
                    "body": (
                        f"{participant} завершил(а) «{activity_card['title']}» "
                        f"с результатом {float(session.percent_score or 0):.0f}%."
                    ),
                    "at": session.completed_at,
                    "link": activity_card["analytics_url"],
                    "link_label": "Открыть аналитику",
                }
            )
        elif session.status == ActivitySession.Status.STARTED:
            events.append(
                {
                    "kind": "started",
                    "title": "Начата сессия",
                    "body": f"{participant} открыл(а) «{activity_card['title']}» и начал(а) прохождение.",
                    "at": session.started_at,
                    "link": activity_card["analytics_url"],
                    "link_label": "Смотреть активность",
                }
            )

    for activity_card in activity_cards[:12]:
        # published_at is kept after unpublishing, so only a live activity gets this event.
        if activity_card["is_published"] and activity_card["published_at"]:
            events.append(
                {
                    "kind": "published",
                    "title": "Активность опубликована",
                    "body": f"«{activity_card['title']}» доступна по ссылке и готова к запуску.",
                    "at": activity_card["published_at"],
                    "link": activity_card["edit_url"],
                    "link_label": "Открыть редактор",
                }
            )

        published_at = activity_card["published_at"]
        updated_at = activity_card["updated_at"]
        if updated_at and (not published_at or abs((updated_at - published_at).total_seconds()) > 1):
            events.append(
                {
                    "kind": "updated",
                    "title": "Интерактив обновлён" if activity_card["is_published"] else "Черновик обновлён",
                    "body": f"Последние правки по активности «{activity_card['title']}» сохранены в редакторе.",
                    "at": updated_at,
                    "link": activity_card["edit_url"],
                    "link_label": "Продолжить редактирование",
                }
            )

    events.sort(key=lambda event: event["at"], reverse=True)
    return events[:6]


def _participant_label(participant_name: str, participant_user) -> str:
    if participant_name:
        return participant_name
    if participant_user:
        full_name = " ".join(
            value for value in (participant_user.first_name, participant_user.last_name) if value
        ).strip()
        return full_name or participant_user.username
    return "Анонимный ученик"


def _format_duration(duration: timedelta | None) -> str:
    if not duration:
        return "—"

    total_seconds = max(int(duration.total_seconds()), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours} ч {minutes} мин"
    if minutes and seconds:
        return f"{minutes} мин {seconds} сек"
    if minutes:
        return f"{minutes} мин"
    return f"{seconds} сек"


def _session_duration(session: ActivitySession) -> timedelta | None:
    if not session.completed_at or not session.started_at:
        return None
    return session.completed_at - session.started_at


def _build_question_performance(activity: Activity) -> tuple[list[dict], list[dict], list[dict]]:
    ordered_items = normalize_question_bank(activity.config_json)
    ordered_lookup = {
        item.get("id"): {
            "index": index,
            "prompt": item.get("prompt") or f"Задание {index}",
        }
        for index, item in enumerate(ordered_items, start=1)
    }
    # One row per question id: answers saved before the teacher edited the wording stay in the same row.
    answer_stats = list(
        ActivityAnswer.objects.filter(session__activity=activity)
        .values("item_key")
        .annotate(
            saved_prompt=Max("prompt"),
            total_answers=Count("id"),
            correct_answers=Count("id", filter=Q(is_correct=True)),
            incorrect_answers=Count("id", filter=Q(is_correct=False)),
        )
    )

    items: list[dict] = []
    for answer_stat in answer_stats:
        ordered_meta = ordered_lookup.get(answer_stat["item_key"], {})
        saved_prompt = (answer_stat["saved_prompt"] or "").strip()
        if ordered_meta:
            prompt = ordered_meta["prompt"]
        else:
            prompt = f"{saved_prompt or 'Задание'} (вопрос удалён)"
        total_answers = answer_stat["total_answers"] or 0
        correct_answers = answer_stat["correct_answers"] or 0
        incorrect_answers = answer_stat["incorrect_answers"] or 0
        accuracy = round((correct_answers / total_answers) * 100) if total_answers else 0
        items.append(
            {
                "item_key": answer_stat["item_key"],
                "index": ordered_meta.get("index", len(items) + 1),
                "prompt": prompt,
                "total_answers": total_answers,
                "correct_answers": correct_answers,
                "incorrect_answers": incorrect_answers,
                "accuracy": accuracy,
                "mistake_note": (
                    _count_label(incorrect_answers, "ошибка", "ошибки", "ошибок") + f" · {accuracy}% точность"
                ),
                "success_note": (
                    _count_label(correct_answers, "верный ответ", "верных ответа", "верных ответов")
                    + f" · {accuracy}% точность"
                ),
            }
        )

    weakest_items = sorted(
        (item for item in items if item["incorrect_answers"]),
        key=lambda item: (-item["incorrect_answers"], -item["total_answers"], item["prompt"]),
    )[:3]
    strongest_items = sorted(
        (item for item in items if item["correct_answers"]),
        key=lambda item: (-item["correct_answers"], -item["total_answers"], item["prompt"]),
    )[:3]

    item_lookup = {item["item_key"]: item for item in items}
    chart_source: list[dict] = []
    for index, ordered_item in enumerate(ordered_items, start=1):
        item_key = ordered_item.get("id")
        item_stat = item_lookup.get(item_key)
        correct_answers = item_stat["correct_answers"] if item_stat else 0
        total_answers = item_stat["total_answers"] if item_stat else 0
        prompt = ordered_item.get("prompt") or (item_stat["prompt"] if item_stat else f"Задание {index}")
        chart_source.append(
            {
                "index": index,
                "prompt": prompt,
                "correct_answers": correct_answers,
                "total_answers": total_answers,
            }
        )

    return weakest_items, strongest_items, chart_source


def _chart_axis_step(count: int) -> int:
    # Past a dozen questions only every 2nd/5th/10th number fits under the line.
    if count <= 12:
        return 1
    if count <= 24:
        return 2
    if count <= 60:
        return 5
    return 10


def _build_success_chart(success_chart_items: list[dict]) -> dict | None:
    # Without a single answer the line would lie flat at zero; the template shows an empty state instead.
    if not any(item["total_answers"] for item in success_chart_items):
        return None

    width = 760
    height = 320
    left_padding = 44
    right_padding = 44
    top_padding = 44
    bottom_padding = 56
    baseline_y = height - bottom_padding
    axis_label_y = baseline_y + 34
    plot_width = max(width - left_padding - right_padding, 1)
    plot_height = max(baseline_y - top_padding, 1)
    max_success = max(item["correct_answers"] for item in success_chart_items)
    count = len(success_chart_items)
    axis_step = _chart_axis_step(count)

    points: list[dict] = []
    for position, item in enumerate(success_chart_items):
        if count == 1:
            x = width / 2
        else:
            x = left_padding + (plot_width * position / (count - 1))
        ratio = item["correct_answers"] / max_success if max_success else 0
        y = baseline_y - (ratio * plot_height)
        index = item["index"]
        if axis_step == 1 or index == 1 or index % axis_step == 0:
            # «Задание N» is too wide for more than five points, so the axis falls back to bare numbers.
            axis_label = f"Задание {index}" if count <= 5 else str(index)
        else:
            axis_label = ""
        if item["total_answers"]:
            result_label = (
                _count_label(item["correct_answers"], "верный ответ", "верных ответа", "верных ответов")
                + f" из {item['total_answers']}"
            )
        else:
            result_label = "пока нет ответов"
        # Coordinates go to the template as strings: the ru locale would print floats with a comma.
        points.append(
            {
                **item,
                "x": round(x, 2),
                "y": round(y, 2),
                "x_svg": f"{x:.2f}",
                "y_svg": f"{y:.2f}",
                "label_y_svg": f"{y - 20:.2f}",
                "axis_label": axis_label,
                "tooltip": f"Задание {index} · {item['prompt']} · {result_label}",
            }
        )

    def smooth_path(source_points: list[dict]) -> str:
        if len(source_points) == 1:
            point = source_points[0]
            return f"M {point['x']} {point['y']} L {point['x']} {point['y']}"

        segments = [f"M {source_points[0]['x']} {source_points[0]['y']}"]
        for index in range(len(source_points) - 1):
            previous_point = source_points[index - 1] if index > 0 else source_points[index]
            current_point = source_points[index]
            next_point = source_points[index + 1]
            following_point = (
                source_points[index + 2] if index + 2 < len(source_points) else next_point
            )
            control_one_x = current_point["x"] + (next_point["x"] - previous_point["x"]) / 6
            control_one_y = current_point["y"] + (next_point["y"] - previous_point["y"]) / 6
            control_two_x = next_point["x"] - (following_point["x"] - current_point["x"]) / 6
            control_two_y = next_point["y"] - (following_point["y"] - current_point["y"]) / 6
            segments.append(
                "C "
                f"{control_one_x:.2f} {control_one_y:.2f}, "
                f"{control_two_x:.2f} {control_two_y:.2f}, "
                f"{next_point['x']:.2f} {next_point['y']:.2f}"
            )
        return " ".join(segments)

    line_path = smooth_path(points)
    area_path = (
        f"{line_path} "
        f"L {points[-1]['x']} {baseline_y:.2f} "
        f"L {points[0]['x']} {baseline_y:.2f} Z"
    )

    return {
        "width": width,
        "height": height,
        "grid_lines_svg": [f"{top_padding + plot_height * step / 4:.2f}" for step in range(5)],
        "axis_label_y_svg": f"{axis_label_y:.2f}",
        "points": points,
        "line_path": line_path,
        "area_path": area_path,
        "max_success": max_success,
        "max_success_label": _count_label(max_success, "успех", "успеха", "успехов"),
        "success_note": (
            "Линия показывает, на каких заданиях ученики чаще справлялись успешно: "
            "чем выше точка, тем больше успешных выполнений."
        ),
    }


def _build_top_students(completed_sessions: list[ActivitySession]) -> list[dict]:
    top_students: list[dict] = []
    seen_labels: set[str] = set()

    for rank, session in enumerate(
        sorted(
            completed_sessions,
            key=lambda current: (
                -(float(current.percent_score or 0)),
                -current.score,
                current.completed_at or current.started_at,
            ),
        ),
        start=1,
    ):
        participant_label = _participant_label(session.participant_name, session.participant_user)
        participant_key = participant_label.casefold()
        if participant_key in seen_labels:
            continue
        seen_labels.add(participant_key)
        top_students.append(
            {
                "rank": len(top_students) + 1,
                "name": participant_label,
                "score_label": f"{float(session.percent_score or 0):.0f}%",
                "result_label": f"{session.score} из {session.max_score}",
                "duration_label": _format_duration(_session_duration(session)),
            }
        )
        if len(top_students) == 3:
            break

    return top_students


def landing(request):
    if request.user.is_authenticated:
        return redirect(user_home_url(request.user))

    context = {
        "features": LANDING_FEATURES,
        "template_cards": LANDING_TEMPLATE_CARDS,
        "showcases": LANDING_SHOWCASES,
        "footer_columns": [
            {
                "title": "Платформа",
                "links": [
                    {"label": "Преимущества", "href": "#features"},
                    {"label": "Шаблоны", "href": "#templates"},
                    {"label": "Как это работает", "href": "#results"},
                ],
            },
            {
                "title": "Аккаунт",
                "links": [
                    {"label": "Регистрация", "href": reverse("accounts:register")},
                    {"label": "Вход", "href": reverse("accounts:login")},
                ],
            },
            {
                "title": "Запуск",
                "links": [
                    {"label": "Начать бесплатно", "href": reverse("accounts:register")},
                    {"label": "Открыть шаблоны", "href": "#templates"},
                    {"label": "Вернуться наверх", "href": "#top"},
                ],
            },
        ],
    }
    return render(request, "dashboard/landing.html", context)


@teacher_required
def home(request):
    profile = getattr(request, "user_profile", ensure_user_profile(request.user))
    activities = (
        Activity.objects.filter(owner=request.user)
        .prefetch_related(
            Prefetch(
                "share_links",
                queryset=ShareLink.objects.filter(is_active=True).order_by("-created_at"),
                to_attr="dashboard_active_share_links",
            )
        )
        .order_by("-updated_at")
    )
    all_activity_cards = [_build_activity_card(activity, request) for activity in activities]
    query = request.GET.get("q", "").strip()
    activity_cards = (
        [activity_card for activity_card in all_activity_cards if _matches_dashboard_query(activity_card, query)]
        if query
        else all_activity_cards
    )

    activity_ids = [activity_card["id"] for activity_card in activity_cards]
    if activity_ids:
        session_summary = ActivitySession.objects.filter(activity_id__in=activity_ids).aggregate(
            launches=Count("id"),
            active_sessions=Count("id", filter=Q(status=ActivitySession.Status.STARTED)),
            completions=Count("id", filter=Q(status=ActivitySession.Status.COMPLETED)),
            average_score=Avg("percent_score", filter=Q(status=ActivitySession.Status.COMPLETED)),
        )
    else:
        session_summary = {
            "launches": 0,
            "active_sessions": 0,
            "completions": 0,
            "average_score": 0,
        }

    total_activities = len(activity_cards)
    # The month boundary follows the teacher's clock (TIME_ZONE), not UTC.
    month_start = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    created_this_month = sum(
        1 for activity_card in activity_cards if activity_card["created_at"] >= month_start
    )
    average_score = float(session_summary["average_score"] or 0)
    teacher_display_name = profile_short_name(request.user, profile)

    if query:
        hero_text = (
            f"По запросу «{query}» {plural_form(total_activities, 'найдена', 'найдено', 'найдено')} "
            f"{_count_label(total_activities, 'активность', 'активности', 'активностей')}. "
            "Цифры и лента событий показывают только найденное."
        )
    elif total_activities:
        hero_text = (
            f"Сейчас у вас {_count_label(session_summary['launches'] or 0, 'запуск', 'запуска', 'запусков')}, "
            f"{_count_label(session_summary['completions'] or 0, 'завершение', 'завершения', 'завершений')} и "
            f"{_count_label(session_summary['active_sessions'] or 0, 'активная сессия', 'активные сессии', 'активных сессий')} "
            "по сохранённым активностям."
        )
    else:
        hero_text = (
            "Пока здесь нет активностей. Создайте первый интерактив, "
            "чтобы увидеть метрики, карточки и последние события класса."
        )

    summary_cards = [
        {
            "tone": "violet",
            "label": "Всего активностей",
            "value": total_activities,
            "note": _count_label(
                created_this_month,
                "новая активность",
                "новые активности",
                "новых активностей",
            )
            + " в этом месяце",
            "icon": "stack",
        },
        {
            "tone": "indigo",
            "label": "Активные сессии",
            "value": session_summary["active_sessions"] or 0,
            "note": _count_label(session_summary["launches"] or 0, "запуск", "запуска", "запусков")
            + " всего",
            "icon": "pulse",
        },
        {
            "tone": "apricot",
            "label": "Средний результат",
            "value": f"{average_score:.1f}%".replace(".", ",") if session_summary["completions"] else "—",
            "note": (
                _count_label(
                    session_summary["completions"] or 0,
                    "завершение",
                    "завершения",
                    "завершений",
                )
                + " в выборке"
                if session_summary["completions"]
                else "Пока нет завершённых прохождений"
            ),
            "icon": "spark",
            "progress": average_score,
        },
    ]

    context = {
        "q": query,
        "teacher_display_name": teacher_display_name,
        "teacher_initial": profile_initials(request.user, profile),
        "teacher_avatar_url": profile.avatar.url if profile.avatar else "",
        "teacher_short_name": teacher_display_name,
        "hero_text": hero_text,
        "summary_cards": summary_cards,
        "recent_activities": activity_cards,
        "recent_events": _build_recent_events(activity_cards),
        "recent_activity_heading": "Результаты поиска" if query else "Все активности",
        "search_result_count": total_activities,
        "has_activity_results": bool(activity_cards),
    }
    return render(request, "dashboard/home.html", context)


@teacher_required
def activity_analytics(request, pk: int):
    activity = get_object_or_404(Activity, pk=pk, owner=request.user)
    profile = getattr(request, "user_profile", ensure_user_profile(request.user))
    sessions = list(activity.sessions.select_related("participant_user").all())
    completed_sessions = [
        session for session in sessions if session.status == ActivitySession.Status.COMPLETED
    ]
    completed_durations = [
        duration
        for duration in (_session_duration(session) for session in completed_sessions)
        if duration is not None
    ]
    average_duration = (
        timedelta(seconds=sum(duration.total_seconds() for duration in completed_durations) / len(completed_durations))
        if completed_durations
        else None
    )
    weakest_items, strongest_items, success_chart_items = _build_question_performance(activity)
    sessions_summary = activity.sessions.aggregate(
        avg_percent=Avg("percent_score", filter=Q(status=ActivitySession.Status.COMPLETED))
    )
    session_rows = [
        {
            "participant": _participant_label(session.participant_name, session.participant_user),
            "status": session.get_status_display(),
            "score_label": f"{session.score} / {session.max_score}",
            "percent_label": f"{float(session.percent_score or 0):.0f}%",
            "started_at": session.started_at,
            "completed_at": session.completed_at,
            "duration_label": _format_duration(_session_duration(session)),
        }
        for session in sessions
    ]
    teacher_display_name = profile_short_name(request.user, profile)
    success_chart = _build_success_chart(success_chart_items)
    # The empty chart state hands the teacher the link to send, but only a published activity has a working one.
    share_link = activity.active_share_link if not success_chart and activity.is_published else None

    return render(
        request,
        "dashboard/analytics.html",
        {
            "activity": activity,
            "activity_template_title": _dashboard_template_title(activity.template_key),
            "teacher_display_name": teacher_display_name,
            "teacher_initial": profile_initials(request.user, profile),
            "teacher_avatar_url": profile.avatar.url if profile.avatar else "",
            "sessions": session_rows,
            "launches": len(sessions),
            "launches_label": _count_label(len(sessions), "запуск", "запуска", "запусков"),
            "completions": len(completed_sessions),
            "average_score": float(sessions_summary["avg_percent"] or 0) if completed_sessions else None,
            "average_duration": _format_duration(average_duration),
            "average_duration_note": (
                _count_label(len(completed_durations), "завершение", "завершения", "завершений") + " в расчёте"
                if completed_durations
                else "Появится после первого завершённого прохождения."
            ),
            "success_chart": success_chart,
            "share_url": request.build_absolute_uri(share_link.get_absolute_url()) if share_link else "",
            "top_students": _build_top_students(completed_sessions),
            "weakest_items": weakest_items,
            "strongest_items": strongest_items,
        },
    )
