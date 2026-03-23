from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from activities.forms import ActivityForm
from activities.models import Activity
from activities.services import duplicate_activity, ensure_share_link
from interactive_templates.registry import registry


def _selected_template_key(request, activity: Activity | None = None) -> str:
    if request.method == "POST":
        return request.POST.get("template_key") or (activity.template_key if activity else registry.default_key())
    if request.GET.get("template_key"):
        return request.GET["template_key"]
    if activity:
        return activity.template_key
    return registry.default_key()


def _activity_editor(request, activity: Activity | None = None):
    selected_key = _selected_template_key(request, activity)
    if selected_key not in registry.keys():
        selected_key = registry.default_key()
    definition = registry.get(selected_key)

    if request.method == "POST":
        activity_form = ActivityForm(request.POST, instance=activity)
        config_form = definition.get_editor_form(request.POST)
        if activity_form.is_valid() and config_form.is_valid():
            candidate = activity_form.save(commit=False)
            candidate.owner = request.user
            candidate.template_key = selected_key
            candidate.config_json = definition.build_config(config_form.cleaned_data)
            definition.validate_config(candidate.config_json)

            action = request.POST.get("action", "save_draft")
            if action == "publish":
                if definition.metadata.playable:
                    candidate.publish()
                else:
                    activity_form.add_error(
                        "template_key",
                        "This template is registered, but the public runtime is not implemented yet.",
                    )
            else:
                candidate.unpublish()

            if not activity_form.errors:
                candidate.save()
                if candidate.is_published:
                    ensure_share_link(candidate)
                    messages.success(request, "Activity saved and published.")
                else:
                    messages.success(request, "Draft saved.")
                return redirect("activities:edit", pk=candidate.pk)
    else:
        config = (
            activity.config_json
            if activity and activity.template_key == selected_key
            else definition.default_config()
        )
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
    messages.success(request, "Activity duplicated as a new draft.")
    return redirect("activities:edit", pk=duplicated.pk)


@login_required
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
