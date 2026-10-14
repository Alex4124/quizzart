from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from accounts.services import ensure_user_profile, profile_full_name
from activities.models import Activity, ShareLink
from attempts.forms import LaunchForm
from attempts.models import ActivitySession
from attempts.presentation import build_player_shell_context
from attempts.services import apply_evaluation
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


def _get_share_link_or_404(slug: str, *, require_published: bool = True) -> ShareLink:
    share_link = get_object_or_404(
        ShareLink.objects.select_related("activity"),
        slug=slug,
        is_active=True,
    )
    if require_published and share_link.activity.status != Activity.Status.PUBLISHED:
        raise Http404("Интерактив не опубликован.")
    return share_link


def _get_definition_or_404(activity: Activity):
    if activity.template_key not in registry.keys():
        raise Http404("Шаблон интерактива больше не поддерживается.")
    return registry.get(activity.template_key)


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


def _finish_run(request, slug: str, session: ActivitySession) -> None:
    request.session[_result_session_key(slug)] = str(session.token)
    request.session.pop(_active_session_key(slug), None)


def _action_payload(action: str, activity, definition, session, evaluation, outcome, results_url: str) -> dict:
    """The JSON a player gets back: feedback on its answer and the recomputed run, never the answer key."""
    config = activity.config_json
    payload = {
        "ok": True,
        "action": action,
        "item_key": evaluation.item_key,
        "already_answered": False,
        "feedback": None,
        "answered_count": outcome.answered_count,
        "total_count": outcome.total_count,
        "is_complete": outcome.is_complete,
        "redirect_url": results_url if outcome.is_complete else None,
    }
    if evaluation.item_key and evaluation.item_key in outcome.stored:
        answer, created = outcome.stored[evaluation.item_key]
        item = next((item for item in definition.get_items(config) if item["id"] == evaluation.item_key), None)
        payload["already_answered"] = not created
        payload["feedback"] = definition.build_answer_feedback(config, item, answer)
    if getattr(definition, "reveals_correctness", lambda _config: True)(config):
        payload.update(
            {
                "score": session.score,
                "max_score": session.max_score,
                "percent_score": float(session.percent_score),
            }
        )
    else:
        # The running score would tell which answers were right when the template hides correctness.
        payload.update({"score": None, "max_score": session.max_score, "percent_score": None})
    payload.update(evaluation.response)
    return payload


def _handle_session_action(request, share_link: ShareLink, definition):
    slug = share_link.slug
    activity = share_link.activity
    is_ajax = _is_ajax_request(request)
    play_url = reverse("attempts:play", kwargs={"slug": slug})
    results_url = reverse("attempts:results", kwargs={"slug": slug})
    token = request.session.get(_active_session_key(slug))

    try:
        with transaction.atomic():
            session = ActivitySession.objects.select_for_update().get(share_link=share_link, token=token)
            if session.status == ActivitySession.Status.COMPLETED:
                evaluation = outcome = None
            else:
                evaluation = definition.evaluate_submission(activity, session, request.POST)
                outcome = apply_evaluation(session, activity, definition, evaluation)
    except (ActivitySession.DoesNotExist, ValidationError) as exc:
        if isinstance(exc, ValidationError):
            message, status, target = exc.messages[0], 400, None
        else:
            message, status, target = "Прохождение не найдено. Начните заново.", 409, play_url
        if is_ajax:
            return JsonResponse({"ok": False, "error": message, "redirect_url": target}, status=status)
        messages.error(request, message)
        return redirect(play_url)

    if outcome is None:
        _finish_run(request, slug, session)
        if is_ajax:
            return JsonResponse(
                {"ok": False, "error": "Прохождение уже завершено.", "redirect_url": results_url},
                status=409,
            )
        return redirect(results_url)

    if outcome.is_complete:
        _finish_run(request, slug, session)
    if is_ajax:
        action = str(request.POST.get("action", ""))
        return JsonResponse(_action_payload(action, activity, definition, session, evaluation, outcome, results_url))
    return redirect(results_url if outcome.is_complete else play_url)


def play(request, slug: str):
    share_link = _get_share_link_or_404(slug)
    activity = share_link.activity
    definition = _get_definition_or_404(activity)
    student_profile, student_name = _get_student_identity(request)

    if not definition.metadata.playable:
        runtime = definition.build_runtime_data(activity)
        return render(
            request,
            "player/not_implemented.html",
            _player_context(request, activity, definition, runtime, mode="launch", participant_name=student_name),
        )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "restart":
            request.session.pop(_active_session_key(slug), None)
            request.session.pop(_result_session_key(slug), None)
            return redirect("attempts:play", slug=slug)

        if action == "start":
            current_session = _get_current_session(request, share_link)
            if current_session and current_session.status == ActivitySession.Status.COMPLETED:
                _finish_run(request, slug, current_session)
                return redirect("attempts:results", slug=slug)
            if not current_session:
                form = LaunchForm(request.POST)
                if not form.is_valid():
                    runtime = definition.build_runtime_data(activity)
                    return render(
                        request,
                        "player/launch.html",
                        {
                            **_player_context(
                                request, activity, definition, runtime, mode="launch", participant_name=student_name
                            ),
                            "share_link": share_link,
                            "form": form,
                        },
                    )
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

        return _handle_session_action(request, share_link, definition)

    current_session = _get_current_session(request, share_link)
    if current_session and current_session.status == ActivitySession.Status.COMPLETED:
        _finish_run(request, slug, current_session)
        return redirect("attempts:results", slug=slug)

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
    runtime["action_url"] = reverse("attempts:play", kwargs={"slug": slug})
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
    # A finished run stays viewable to its student after the teacher unpublishes the activity.
    share_link = _get_share_link_or_404(slug, require_published=False)
    activity = share_link.activity
    definition = _get_definition_or_404(activity)
    result_session = _get_result_session(request, share_link)
    if not result_session:
        if not activity.is_published:
            raise Http404("Интерактив не опубликован.")
        return redirect("attempts:play", slug=slug)

    runtime = definition.build_runtime_data(activity, session=result_session)
    runtime.update(definition.build_results_data(activity, result_session))
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
