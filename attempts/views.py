from __future__ import annotations

from django.core.exceptions import ValidationError
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from accounts.services import ensure_user_profile, profile_full_name
from activities.models import Activity, ShareLink
from attempts.forms import LaunchForm
from attempts.models import ActivitySession
from attempts.presentation import build_player_shell_context
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


def _get_student_identity(request) -> tuple[object | None, str]:
    if not request.user.is_authenticated:
        return None, ""
    profile = ensure_user_profile(request.user)
    if not profile.is_student:
        return None, ""
    return profile, profile_full_name(request.user, profile)


def _is_ajax_request(request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _player_context(
    request,
    activity: Activity,
    definition,
    runtime: dict,
    *,
    session: ActivitySession | None = None,
    preview: bool = False,
    mode: str = "play",
    participant_name: str = "",
) -> dict:
    return {
        "activity": activity,
        "template_definition": definition,
        "runtime": runtime,
        "session": session,
        "preview": preview,
        "player_shell": build_player_shell_context(
            request,
            activity,
            definition,
            runtime,
            session=session,
            preview=preview,
            mode=mode,
            participant_name=participant_name,
        ),
    }


def play(request, slug: str):
    share_link = _get_share_link_or_404(slug)
    activity = share_link.activity
    definition = registry.get(activity.template_key)
    student_profile, student_name = _get_student_identity(request)

    if not definition.metadata.playable:
        runtime = definition.build_runtime_data(activity)
        return render(
            request,
            "player/not_implemented.html",
            _player_context(request, activity, definition, runtime, mode="launch", participant_name=student_name),
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
                    participant_name = form.cleaned_data["participant_name"].strip() or student_name
                    current_session = ActivitySession.objects.create(
                        activity=activity,
                        share_link=share_link,
                        participant_name=participant_name,
                        participant_user=request.user if student_profile else None,
                        max_score=definition.get_max_score(activity.config_json),
                    )
                    request.session[_active_session_key(slug)] = str(current_session.token)
            return redirect("attempts:play", slug=slug)

        if not current_session:
            return redirect("attempts:play", slug=slug)

        try:
            evaluation = definition.evaluate_submission(activity, current_session, request.POST)
        except ValidationError as exc:
            if _is_ajax_request(request):
                return JsonResponse({"ok": False, "error": exc.messages[0]}, status=400)
            runtime = definition.build_runtime_data(activity, session=current_session)
            return render(
                request,
                definition.player_template_name,
                {
                    **_player_context(
                        request,
                        activity,
                        definition,
                        runtime,
                        session=current_session,
                        mode="play",
                        participant_name=current_session.participant_name or student_name,
                    ),
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
            if _is_ajax_request(request):
                return JsonResponse(
                    {
                        "ok": True,
                        "is_complete": True,
                        "score": current_session.score,
                        "max_score": current_session.max_score,
                        "percent_score": float(current_session.percent_score),
                        "redirect_url": redirect("attempts:results", slug=slug).url,
                    }
                )
            return redirect("attempts:results", slug=slug)
        if _is_ajax_request(request):
            return JsonResponse(
                {
                    "ok": True,
                    "is_complete": False,
                    "score": current_session.score,
                    "max_score": current_session.max_score,
                    "percent_score": float(current_session.percent_score),
                }
            )
        return redirect("attempts:play", slug=slug)

    if not current_session:
        runtime = definition.build_runtime_data(activity)
        return render(
            request,
            "player/launch.html",
            {
                **_player_context(request, activity, definition, runtime, mode="launch", participant_name=student_name),
                "share_link": share_link,
                "form": LaunchForm(initial={"participant_name": student_name}),
            },
        )

    runtime = definition.build_runtime_data(activity, session=current_session)
    return render(
        request,
        definition.player_template_name,
        _player_context(
            request,
            activity,
            definition,
            runtime,
            session=current_session,
            mode="play",
            participant_name=current_session.participant_name or student_name,
        ),
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
        _player_context(
            request,
            activity,
            definition,
            runtime,
            session=result_session,
            mode="results",
            participant_name=result_session.participant_name,
        ),
    )
