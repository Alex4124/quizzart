from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from activities.forms import ActivityForm
from activities.models import Activity
from activities.services import duplicate_activity, ensure_share_link
from interactive_templates.registry import registry


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

    if request.method == "POST":
        activity_form_data = request.POST.copy()
        activity_form_data.setdefault("template_key", selected_key)
        activity_form = ActivityForm(activity_form_data, instance=activity)
        action = request.POST.get("action", "save_draft")

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

                    if action == "publish":
                        if definition.metadata.playable:
                            candidate.publish()
                        else:
                            activity_form.add_error(
                                "template_key",
                                "Этот шаблон зарегистрирован, но публичный runtime еще не реализован.",
                            )
                    else:
                        candidate.unpublish()

                    if not activity_form.errors:
                        candidate.save()
                        if candidate.is_published:
                            ensure_share_link(candidate)
                            messages.success(request, "Интерактив сохранен и опубликован.")
                        else:
                            messages.success(request, "Черновик сохранен.")
                        return redirect("activities:edit", pk=candidate.pk)
    else:
        config = _config_source(definition, activity)
        activity_form = ActivityForm(instance=activity, initial={"template_key": selected_key})
        config_form = definition.get_editor_form(config=config)

    share_link = activity.active_share_link if activity else None
    share_url = request.build_absolute_uri(share_link.get_absolute_url()) if share_link else ""
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
        },
    )


@login_required
def create_activity(request):
    return _activity_editor(request)


@login_required
def edit_activity(request, pk: int):
    activity = get_object_or_404(Activity, pk=pk, owner=request.user)
    return _activity_editor(request, activity=activity)


@login_required
def duplicate_activity_view(request, pk: int):
    activity = get_object_or_404(Activity, pk=pk, owner=request.user)
    duplicated = duplicate_activity(activity)
    messages.success(request, "Интерактив продублирован в новый черновик.")
    return redirect("activities:edit", pk=duplicated.pk)


@login_required
@require_POST
def delete_activity(request, pk: int):
    activity = get_object_or_404(Activity, pk=pk, owner=request.user)
    activity_title = activity.title
    activity.delete()
    messages.success(request, f'Интерактив "{activity_title}" удален.')
    return redirect("dashboard:home")


@login_required
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
