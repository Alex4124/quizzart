from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from accounts.decorators import teacher_required
from activities.forms import ActivityForm
from activities.models import Activity
from activities.services import duplicate_activity, ensure_share_link
from interactive_templates.registry import registry


EDITOR_TAB_CHOICES = (
    ("general", "Общие настройки", "gear"),
    ("content", "Контент / Вопросы", "questions"),
    ("settings", "Параметры шаблона", "palette"),
    ("publish", "Публикация", "publish"),
)

EDITOR_TEMPLATE_STYLES = {
    "quiz": {"tone": "violet", "icon": "quiz"},
    "wheel_of_fortune": {"tone": "apricot", "icon": "wheel"},
    "matching": {"tone": "indigo", "icon": "matching"},
    "categorize": {"tone": "sage", "icon": "categorize"},
    "choose_a_box": {"tone": "lilac", "icon": "boxes"},
    "snake": {"tone": "teal", "icon": "snake"},
}


def _editor_template_cards(selected_key: str) -> list[dict]:
    cards = []
    for definition in registry.all():
        style = EDITOR_TEMPLATE_STYLES.get(definition.metadata.key, {"tone": "default", "icon": "spark"})
        cards.append(
            {
                "key": definition.metadata.key,
                "title": definition.metadata.title,
                "description": definition.metadata.description,
                "playable": definition.metadata.playable,
                "tone": style["tone"],
                "icon": style["icon"],
                "is_selected": definition.metadata.key == selected_key,
            }
        )
    return cards


def _editor_stepper(activity: Activity | None) -> list[dict]:
    current_index = 1
    if activity:
        current_index = 3 if activity.is_published else 2

    steps = []
    for index, (key, label) in enumerate(
        (
            ("draft", "Draft"),
            ("configured", "Configured"),
            ("published", "Published"),
        ),
        start=1,
    ):
        if index < current_index:
            state = "complete"
        elif index == current_index:
            state = "current"
        else:
            state = "upcoming"
        steps.append(
            {
                "key": key,
                "label": label,
                "index": index,
                "state": state,
                "is_current": index == current_index,
            }
        )
    return steps


def _determine_active_tab(request, activity_form, config_form, action: str) -> str:
    valid_tabs = {tab_key for tab_key, _, _ in EDITOR_TAB_CHOICES}
    requested_tab = ""
    if request.method == "POST":
        requested_tab = request.POST.get("active_tab", "").strip()
    else:
        requested_tab = request.GET.get("tab", "").strip()

    if action == "switch_template":
        return "general"

    question_bank_has_errors = any(
        field_name in config_form.fields and config_form[field_name].errors
        for field_name in ("items_json", "items_text")
    )
    visible_config_errors = False

    for field in config_form.visible_fields():
        if field.errors:
            visible_config_errors = True

    if any(field.errors for field in activity_form.visible_fields()):
        return "general"
    if question_bank_has_errors or config_form.non_field_errors():
        return "content"
    if visible_config_errors:
        return "settings"
    if requested_tab in valid_tabs:
        return requested_tab
    return "general"


def _build_tab_links(selected_key: str, activity: Activity | None) -> dict[str, str]:
    links = {}
    for tab_key, _, _ in EDITOR_TAB_CHOICES:
        params = {"tab": tab_key}
        if activity or selected_key:
            params["template_key"] = selected_key
        links[tab_key] = f"?{urlencode(params)}#editor-workspace"
    return links


def _selected_template_key(request, activity: Activity | None = None) -> str:
    if request.method == "POST":
        if request.POST.get("template_key"):
            return request.POST["template_key"]
        if request.GET.get("template_key"):
            return request.GET["template_key"]
        return activity.template_key if activity else registry.default_key()
    if request.GET.get("template_key"):
        return request.GET["template_key"]
    if activity:
        return activity.template_key
    return registry.default_key()


def _config_source(definition, activity: Activity | None) -> dict:
    if activity:
        return activity.config_json
    return definition.default_config()


def _switch_config_form(definition, post_data, activity: Activity | None):
    source_config = _config_source(definition, activity)
    initial = definition.build_editor_initial(source_config)
    prototype_form = definition.get_editor_form(config=source_config)

    for field_name, field in prototype_form.fields.items():
        if getattr(field.widget, "input_type", "") == "checkbox":
            initial[field_name] = field_name in post_data
        elif field_name in post_data:
            initial[field_name] = post_data.get(field_name)

    return definition.get_editor_form(initial=initial)


def _activity_editor(request, activity: Activity | None = None):
    selected_key = _selected_template_key(request, activity)
    if selected_key not in registry.keys():
        selected_key = registry.default_key()
    definition = registry.get(selected_key)
    action = request.POST.get("action", "save_draft") if request.method == "POST" else ""

    if request.method == "POST":
        activity_form_data = request.POST.copy()
        activity_form_data.setdefault("template_key", selected_key)
        activity_form = ActivityForm(activity_form_data, instance=activity)

        if action == "switch_template":
            config_form = _switch_config_form(definition, request.POST, activity)
        else:
            config_form = definition.get_editor_form(request.POST)
            if activity_form.is_valid() and config_form.is_valid():
                try:
                    candidate_config = definition.build_config(config_form.cleaned_data)
                    definition.validate_config(candidate_config)
                except ValidationError as exc:
                    config_form.add_error(None, exc)
                else:
                    candidate = activity_form.save(commit=False)
                    candidate.owner = request.user
                    candidate.template_key = selected_key
                    candidate.config_json = candidate_config
                    was_published = bool(activity and activity.is_published)

                    if action == "publish":
                        if definition.metadata.playable:
                            candidate.publish()
                        else:
                            activity_form.add_error(
                                "template_key",
                                "Этот шаблон зарегистрирован, но публичный runtime еще не реализован.",
                            )
                    elif action == "save_changes":
                        if was_published:
                            candidate.publish()
                        else:
                            candidate.unpublish()
                    else:
                        candidate.unpublish()

                    if not activity_form.errors:
                        candidate.save()
                        if candidate.is_published:
                            ensure_share_link(candidate)
                            if action == "publish" and was_published:
                                messages.success(request, "Изменения опубликованного интерактива сохранены.")
                            elif action == "publish":
                                messages.success(request, "Интерактив сохранен и опубликован.")
                            elif action == "save_changes":
                                messages.success(request, "Изменения сохранены без снятия публикации.")
                            else:
                                messages.success(request, "Интерактив сохранен и опубликован.")
                        else:
                            if action == "save_changes":
                                messages.success(request, "Изменения черновика сохранены.")
                            elif action == "save_draft" and was_published:
                                messages.success(request, "Интерактив снят с публикации и сохранен как черновик.")
                            else:
                                messages.success(request, "Черновик сохранен.")
                        return redirect("activities:edit", pk=candidate.pk)
    else:
        config = _config_source(definition, activity)
        activity_form = ActivityForm(instance=activity, initial={"template_key": selected_key})
        config_form = definition.get_editor_form(config=config)

    share_link = activity.active_share_link if activity else None
    share_url = request.build_absolute_uri(share_link.get_absolute_url()) if share_link else ""
    template_setting_fields = [
        field for field in config_form.visible_fields() if field.name not in {"items_json", "items_text"}
    ]
    active_tab = _determine_active_tab(request, activity_form, config_form, action)
    tab_links = _build_tab_links(selected_key, activity)
    is_saved = activity is not None and activity.pk is not None
    is_published = bool(activity and activity.is_published)
    preview_url = reverse("activities:preview", kwargs={"pk": activity.pk}) if activity else ""
    stepper = _editor_stepper(activity)
    current_step_key = next((step["key"] for step in stepper if step["is_current"]), "draft")
    return render(
        request,
        "activities/editor.html",
        {
            "activity": activity,
            "activity_form": activity_form,
            "config_form": config_form,
            "template_definition": definition,
            "templates": registry.all(),
            "share_link": share_link,
            "share_url": share_url,
            "editor_mode": "edit" if activity else "create",
            "is_saved": is_saved,
            "is_published": is_published,
            "preview_url": preview_url,
            "template_cards": _editor_template_cards(selected_key),
            "active_tab": active_tab,
            "editor_tabs": [
                {
                    "key": tab_key,
                    "label": label,
                    "icon": icon,
                    "href": tab_links[tab_key],
                    "is_active": tab_key == active_tab,
                }
                for tab_key, label, icon in EDITOR_TAB_CHOICES
            ],
            "editor_steps": stepper,
            "current_step_key": current_step_key,
            "template_setting_fields": template_setting_fields,
            "template_settings_available": bool(template_setting_fields),
            "question_bank_has_errors": bool(
                config_form.non_field_errors()
                or any(
                    field_name in config_form.fields and config_form[field_name].errors
                    for field_name in ("items_json", "items_text")
                )
            ),
            "quick_actions": {
                "dashboard_url": reverse("dashboard:home"),
                "duplicate_url": reverse("activities:duplicate", kwargs={"pk": activity.pk}) if activity else "",
                "analytics_url": reverse("dashboard:analytics", kwargs={"pk": activity.pk}) if activity else "",
                "delete_url": reverse("activities:delete", kwargs={"pk": activity.pk}) if activity else "",
            },
        },
    )


@teacher_required
def create_activity(request):
    return _activity_editor(request)


@teacher_required
def edit_activity(request, pk: int):
    activity = get_object_or_404(Activity, pk=pk, owner=request.user)
    return _activity_editor(request, activity=activity)


@teacher_required
def duplicate_activity_view(request, pk: int):
    activity = get_object_or_404(Activity, pk=pk, owner=request.user)
    duplicated = duplicate_activity(activity)
    messages.success(request, "Интерактив продублирован в новый черновик.")
    return redirect("activities:edit", pk=duplicated.pk)


@teacher_required
@require_POST
def delete_activity(request, pk: int):
    activity = get_object_or_404(Activity, pk=pk, owner=request.user)
    activity_title = activity.title
    activity.delete()
    messages.success(request, f'Интерактив "{activity_title}" удален.')
    return redirect("dashboard:home")


@teacher_required
@xframe_options_sameorigin
def preview_activity(request, pk: int):
    activity = get_object_or_404(Activity, pk=pk, owner=request.user)
    definition = registry.get(activity.template_key)
    runtime = definition.build_runtime_data(activity, preview=True)
    return render(
        request,
        definition.preview_template_name,
        {
            "activity": activity,
            "template_definition": definition,
            "runtime": runtime,
            "preview": True,
        },
    )
