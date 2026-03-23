from __future__ import annotations

from typing import Any

from attempts.models import ActivityAnswer, ActivitySession


def persist_template_answers(
    session: ActivitySession,
    answers: list[dict[str, Any]],
) -> None:
    for answer in answers:
        ActivityAnswer.objects.update_or_create(
            session=session,
            item_key=answer["item_key"],
            defaults={
                "prompt": answer.get("prompt", ""),
                "submitted_value": answer.get("submitted_value", {}),
                "is_correct": answer.get("is_correct", False),
                "score_awarded": answer.get("score_awarded", 0),
            },
        )
