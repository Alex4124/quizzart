from __future__ import annotations

from django.db.models import Avg, Count, Prefetch, Q
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from accounts.decorators import teacher_required
from accounts.services import ensure_user_profile, profile_initials, profile_short_name, user_home_url
from activities.models import Activity, ShareLink
from attempts.models import ActivitySession
from interactive_templates.registry import registry
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
        "eyebrow": "quiz",
        "title": "Классическая викторина",
        "description": "Один правильный ответ, чистая структура и быстрый запуск для проверочных работ.",
        "accent_class": "landing-template-card-violet",
    },
    {
        "eyebrow": "wheel_of_fortune",
        "title": "Колесо фортуны",
        "description": "Случайный выбор вопроса, игровое напряжение и удобный темп для фронтальной работы.",
        "accent_class": "landing-template-card-rose",
    },
    {
        "eyebrow": "matching",
        "title": "Сопоставление",
        "description": "Подходит для терминов, определений, дат и коротких связок в тренировочном режиме.",
        "accent_class": "landing-template-card-apricot",
    },
    {
        "eyebrow": "snake",
        "title": "Змейка-обучалка",
        "description": "Игровой формат, где движение по полю открывает вопросы и удерживает внимание класса.",
        "accent_class": "landing-template-card-lilac",
    },
]

LANDING_SHOWCASES = [
    {
        "eyebrow": "Быстрый старт",
        "title": "Любимо учителями,",
        "accent": "быстро собирается под урок.",
        "description": (
            "Лендинг обещает ровно то, что уже есть в продукте: единый редактор, "
            "публикация по ссылке и сохранение результатов после прохождения."
        ),
        "bullets": [
            "Единый поток: создать, опубликовать и открыть ученикам по ссылке.",
            "Минимум ручной настройки и переиспользуемый банк вопросов.",
            "Серверный рендеринг и мобильная подача без лишнего клиентского кода.",
        ],
        "image": "img/landing-teacher-photo.png",
        "image_alt": "Учитель за ноутбуком на фоне панели с аналитикой.",
        "frame_class": "landing-showcase__frame-photo",
        "image_class": "landing-showcase__image-cover landing-showcase__image-cover-teacher",
    },
    {
        "eyebrow": "Игровая подача",
        "title": "Любимо учениками,",
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
        "image": "img/landing-students-photo.png",
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


def _count_label(value: int, one: str, few: str, many: str) -> str:
    remainder_hundred = value % 100
    remainder_ten = value % 10
    if 11 <= remainder_hundred <= 14:
        form = many
    elif remainder_ten == 1:
        form = one
    elif 2 <= remainder_ten <= 4:
        form = few
    else:
        form = many
    return f"{value} {form}"


def _build_activity_card(activity: Activity) -> dict:
    active_share_links = getattr(activity, "dashboard_active_share_links", [])
    share_link = active_share_links[0] if active_share_links else None
    template_title = _dashboard_template_title(activity.template_key)
    question_count = len(normalize_question_bank(activity.config_json, default_points=1))

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
        "question_count_label": f"{question_count} вопросов",
        "cover_variant": _dashboard_cover_variant(activity.template_key),
        "is_published": activity.is_published,
        "edit_url": activity.get_absolute_url(),
        "preview_url": activity.get_preview_url(),
        "analytics_url": reverse("dashboard:analytics", kwargs={"pk": activity.pk}),
        "share_url": share_link.get_absolute_url() if share_link else "",
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
        if activity_card["published_at"]:
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
                    "title": "Черновик обновлён",
                    "body": f"Последние правки по активности «{activity_card['title']}» сохранены в редакторе.",
                    "at": updated_at,
                    "link": activity_card["edit_url"],
                    "link_label": "Продолжить редактирование",
                }
            )

    events.sort(key=lambda event: event["at"], reverse=True)
    return events[:6]


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
        .annotate(
            launches=Count("sessions", distinct=True),
            active_sessions=Count(
                "sessions",
                filter=Q(sessions__status=ActivitySession.Status.STARTED),
                distinct=True,
            ),
            completions=Count(
                "sessions",
                filter=Q(sessions__status=ActivitySession.Status.COMPLETED),
                distinct=True,
            ),
            avg_percent=Avg(
                "sessions__percent_score",
                filter=Q(sessions__status=ActivitySession.Status.COMPLETED),
            ),
        )
        .prefetch_related(
            Prefetch(
                "share_links",
                queryset=ShareLink.objects.filter(is_active=True).order_by("-created_at"),
                to_attr="dashboard_active_share_links",
            )
        )
        .order_by("-updated_at")
    )
    all_activity_cards = [_build_activity_card(activity) for activity in activities]
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
    now = timezone.now()
    created_this_month = sum(
        1
        for activity_card in activity_cards
        if activity_card["created_at"].year == now.year and activity_card["created_at"].month == now.month
    )
    average_score = float(session_summary["average_score"] or 0)
    teacher_display_name = profile_short_name(request.user, profile)

    if query:
        hero_text = (
            f"По запросу «{query}» найдено {total_activities} активностей. "
            "Метрики и лента справа отражают только текущую выборку."
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
            "value": f"{average_score:.1f}%",
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
    sessions = activity.sessions.all()
    summary = sessions.aggregate(avg_percent=Avg("percent_score"))
    return render(
        request,
        "dashboard/analytics.html",
        {
            "activity": activity,
            "sessions": sessions,
            "launches": sessions.count(),
            "completions": sessions.filter(status=ActivitySession.Status.COMPLETED).count(),
            "average_score": summary["avg_percent"] or 0,
        },
    )
