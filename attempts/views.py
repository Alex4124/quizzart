from __future__ import annotations

from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from activities.models import Activity, ShareLink
from attempts.forms import LaunchForm
from attempts.models import ActivitySession
from attempts.services import persist_template_answers
from interactive_templates.registry import registry


def _active_session_key(slug: str) -> str:
    return f"quizzart_play_session_{slug}"


def _result_session_key(slug: str) -> str:
    return f"quizzart_result_session_{slug}"


def _get_current_session(request, share_link: ShareLink) -> ActivitySession | None:
    token = request.session.get(_active_session_key(share_link.slug))
    if not token:
        return None
    return (
        ActivitySession.objects.filter(share_link=share_link, token=token)
        .prefetch_related("answers")
        .first()
    )


def _get_result_session(request, share_link: ShareLink) -> ActivitySession | None:
    token = request.session.get(_result_session_key(share_link.slug))
    if not token:
        return None
    return (
        ActivitySession.objects.filter(share_link=share_link, token=token)
        .prefetch_related("answers")
        .first()
    )


def _get_share_link_or_404(slug: str) -> ShareLink:
    share_link = get_object_or_404(
        ShareLink.objects.select_related("activity"),
        slug=slug,
        is_active=True,
    )
    if share_link.activity.status != Activity.Status.PUBLISHED:
        raise Http404("This activity is not published.")
    return share_link


def play(request, slug: str):
    share_link = _get_share_link_or_404(slug)
    activity = share_link.activity
    definition = registry.get(activity.template_key)

    if not definition.metadata.playable:
        return render(
            request,
            "player/not_implemented.html",
            {
                "activity": activity,
                "template_definition": definition,
                "runtime": definition.build_runtime_data(activity),
            },
        )

    current_session = _get_current_session(request, share_link)
    if current_session and current_session.status == ActivitySession.Status.COMPLETED:
        request.session[_result_session_key(slug)] = str(current_session.token)
        request.session.pop(_active_session_key(slug), None)
        return redirect("attempts:results", slug=slug)

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "restart":
            request.session.pop(_active_session_key(slug), None)
            request.session.pop(_result_session_key(slug), None)
            return redirect("attempts:play", slug=slug)

        if action == "start":
            if not current_session:
                form = LaunchForm(request.POST)
                if form.is_valid():
                    current_session = ActivitySession.objects.create(
                        activity=activity,
                        share_link=share_link,
                        participant_name=form.cleaned_data["participant_name"],
                        max_score=definition.get_max_score(activity.config_json),
                    )
                    request.session[_active_session_key(slug)] = str(current_session.token)
            return redirect("attempts:play", slug=slug)

        if not current_session:
            return redirect("attempts:play", slug=slug)

        try:
            evaluation = definition.evaluate_submission(activity, current_session, request.POST)
        except ValidationError as exc:
            return render(
                request,
                definition.player_template_name,
                {
                    "activity": activity,
                    "template_definition": definition,
                    "runtime": definition.build_runtime_data(activity, session=current_session),
                    "session": current_session,
                    "preview": False,
                    "player_error": exc.messages[0],
                },
            )

        persist_template_answers(current_session, evaluation.answers)
        current_session.runtime_state = evaluation.runtime_state
        current_session.update_scores(evaluation.score, evaluation.max_score)
        save_fields = ["runtime_state", "score", "max_score", "percent_score"]
        if evaluation.is_complete:
            current_session.mark_completed(evaluation.score, evaluation.max_score)
            save_fields.extend(["status", "completed_at"])
        current_session.save(update_fields=save_fields)

        if evaluation.is_complete:
            request.session[_result_session_key(slug)] = str(current_session.token)
            request.session.pop(_active_session_key(slug), None)
            return redirect("attempts:results", slug=slug)
        return redirect("attempts:play", slug=slug)

    if not current_session:
        return render(
            request,
            "player/launch.html",
            {
                "activity": activity,
                "share_link": share_link,
                "form": LaunchForm(),
            },
        )

    runtime = definition.build_runtime_data(activity, session=current_session)
    return render(
        request,
        definition.player_template_name,
        {
            "activity": activity,
            "template_definition": definition,
            "runtime": runtime,
            "session": current_session,
            "preview": False,
        },
    )


def results(request, slug: str):
    share_link = _get_share_link_or_404(slug)
    activity = share_link.activity
    definition = registry.get(activity.template_key)
    result_session = _get_result_session(request, share_link)
    if not result_session:
        return redirect("attempts:play", slug=slug)

    runtime = definition.build_runtime_data(activity, session=result_session)
    return render(
        request,
        "player/results.html",
        {
            "activity": activity,
            "session": result_session,
            "runtime": runtime,
            "template_definition": definition,
        },
    )
