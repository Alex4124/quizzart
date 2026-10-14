from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from attempts.models import ActivityAnswer, ActivitySession


def record_answer(session: ActivitySession, answer: dict[str, Any]) -> tuple[ActivityAnswer, bool]:
    """Save an answer unless the item already has one: the first saved answer is final.

    get_or_create retries the lookup on a unique-constraint race, so a double click never becomes a 500.
    """
    return ActivityAnswer.objects.get_or_create(
        session=session,
        item_key=answer["item_key"],
        defaults={
            "prompt": answer.get("prompt", ""),
            "submitted_value": answer.get("submitted_value", {}),
            "is_correct": answer.get("is_correct", False),
            "score_awarded": answer.get("score_awarded", 0),
        },
    )


@dataclass
class ActionOutcome:
    # item_key -> (saved answer, created by this request)
    stored: dict[str, tuple[ActivityAnswer, bool]] = field(default_factory=dict)
    answered_count: int = 0
    total_count: int = 0
    is_complete: bool = False


def apply_evaluation(session: ActivitySession, activity: Any, definition: Any, evaluation: Any) -> ActionOutcome:
    """Persist one template action and recompute the session from saved answers.

    Call inside transaction.atomic() with the session row locked (select_for_update).
    """
    config = activity.config_json
    outcome = ActionOutcome()
    for row in evaluation.answers:
        outcome.stored[row["item_key"]] = record_answer(session, row)
    if evaluation.runtime_state is not None:
        session.runtime_state = evaluation.runtime_state

    item_ids = {item["id"] for item in definition.get_items(config)}
    # A fresh query: answers to questions the teacher deleted mid-run no longer count.
    current_answers = [answer for answer in session.answers.all() if answer.item_key in item_ids]
    score, max_score = definition.score_answers(config, current_answers)
    answered_keys = {answer.item_key for answer in current_answers}
    outcome.answered_count = len(answered_keys)
    outcome.total_count = len(item_ids)
    outcome.is_complete = evaluation.is_complete or definition.is_complete(config, answered_keys)

    save_fields = ["runtime_state", "score", "max_score", "percent_score"]
    if outcome.is_complete:
        session.mark_completed(score, max_score)
        save_fields.extend(["status", "completed_at"])
    else:
        session.update_scores(score, max_score)
    session.save(update_fields=save_fields)
    return outcome
