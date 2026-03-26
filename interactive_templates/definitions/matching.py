from __future__ import annotations

import random
from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from interactive_templates.base import BaseTemplateDefinition, TemplateEvaluation, TemplateMetadata
from interactive_templates.utils import (
    build_review_items,
    correct_option,
    normalize_question_bank,
    question_bank_items_from_payload,
    serialize_question_bank,
    serialize_question_bank_editor,
)


class MatchingEditorForm(forms.Form):
    shuffle = forms.BooleanField(
        required=False,
        initial=True,
        label="\u041f\u0435\u0440\u0435\u043c\u0435\u0448\u0438\u0432\u0430\u0442\u044c \u043e\u0442\u0432\u0435\u0442\u044b",
    )
    items_json = forms.CharField(required=False, widget=forms.HiddenInput())
    items_text = forms.CharField(required=False, widget=forms.HiddenInput())


def _sample_items() -> list[dict[str, Any]]:
    return [
        {
            "id": f"item-{index}",
            "prompt": f"Match prompt {index}",
            "options": [
                {"id": f"item-{index}-option-1", "text": f"Answer {index}", "is_correct": True},
                {"id": f"item-{index}-option-2", "text": f"Wrong {index}", "is_correct": False},
            ],
            "points": 1,
        }
        for index in range(1, 5)
    ]


class MatchingDefinition(BaseTemplateDefinition):
    metadata = TemplateMetadata(
        key="matching",
        title="\u0421\u043e\u043f\u043e\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u0438\u0435",
        description="\u041d\u0443\u0436\u043d\u043e \u0441\u043e\u043f\u043e\u0441\u0442\u0430\u0432\u0438\u0442\u044c \u043a\u0430\u0436\u0434\u044b\u0439 \u0432\u043e\u043f\u0440\u043e\u0441 \u0441 \u043f\u0440\u0430\u0432\u0438\u043b\u044c\u043d\u044b\u043c \u043e\u0442\u0432\u0435\u0442\u043e\u043c.",
        playable=True,
    )
    editor_form_class = MatchingEditorForm
    player_template_name = "player/matching.html"
    preview_template_name = "player/matching.html"
    editor_question_default_points = 1

    def default_config(self) -> dict[str, Any]:
        return {
            "shuffle": True,
            "items": _sample_items(),
        }

    def build_editor_initial(self, config: dict[str, Any]) -> dict[str, Any]:
        items = normalize_question_bank(config, default_points=1)
        return {
            "shuffle": config.get("shuffle", True),
            "items_json": serialize_question_bank_editor(items, default_points=1),
            "items_text": serialize_question_bank(items, default_points=1),
        }

    def build_config(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "shuffle": cleaned_data.get("shuffle", False),
            "items": question_bank_items_from_payload(
                cleaned_data.get("items_json"),
                cleaned_data.get("items_text", ""),
                default_points=1,
            ),
        }

    def validate_config(self, config: dict[str, Any]) -> None:
        super().validate_config(config)
        items = normalize_question_bank(config, default_points=1)
        answers = [correct_option(item)["text"] for item in items]
        if len(answers) != len(set(answers)):
            raise ValidationError(
                "\u0414\u043b\u044f \u0441\u043e\u043f\u043e\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u0438\u044f \u043f\u0440\u0430\u0432\u0438\u043b\u044c\u043d\u044b\u0435 \u043e\u0442\u0432\u0435\u0442\u044b \u0434\u043e\u043b\u0436\u043d\u044b \u0431\u044b\u0442\u044c \u0443\u043d\u0438\u043a\u0430\u043b\u044c\u043d\u044b\u043c\u0438."
            )

    def build_runtime_data(
        self,
        activity: Any,
        session: Any | None = None,
        preview: bool = False,
    ) -> dict[str, Any]:
        items = normalize_question_bank(activity.config_json, default_points=1)
        answer_map = {}
        if session:
            answer_map = {answer.item_key: answer for answer in session.answers.all()}

        answer_bank = []
        for item in items:
            for option in item["options"]:
                answer_bank.append(
                    {
                        "id": option["id"],
                        "item_id": item["id"],
                        "text": option["text"],
                        "used": False,
                        "is_correct": option.get("is_correct", False),
                    }
                )
        seed_base = "preview" if preview else str(session.token) if session else "matching"
        if activity.config_json.get("shuffle", False):
            random.Random(seed_base).shuffle(answer_bank)

        rows = []
        for item in items:
            answer = answer_map.get(item["id"])
            correct_answer = correct_option(item)
            rows.append(
                {
                    "id": item["id"],
                    "prompt": item["prompt"],
                    "selected": answer.submitted_value.get("choice", "") if answer else "",
                    "correct_choice_id": correct_answer["id"],
                    "correct_choice_text": correct_answer["text"],
                    "correct_option": correct_answer["text"],
                    "points": item.get("points", 1),
                }
            )

        return {
            "rows": rows,
            "answer_bank": answer_bank,
            "choices": [choice["text"] for choice in answer_bank],
            "reveal_correct_answer": True,
            "max_score": self.get_max_score(activity.config_json),
            "review_items": build_review_items(items, answer_map),
        }

    def get_max_score(self, config: dict[str, Any]) -> int:
        items = normalize_question_bank(config, default_points=1)
        return sum(item.get("points", 1) for item in items)

    def evaluate_submission(
        self,
        activity: Any,
        session: Any,
        payload: dict[str, Any],
    ) -> TemplateEvaluation:
        if payload.get("action") != "submit_matching":
            raise ValidationError(
                "\u041d\u0435\u0438\u0437\u0432\u0435\u0441\u0442\u043d\u043e\u0435 \u0434\u0435\u0439\u0441\u0442\u0432\u0438\u0435 \u0434\u043b\u044f \u0448\u0430\u0431\u043b\u043e\u043d\u0430 '\u0421\u043e\u043f\u043e\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u0438\u0435'."
            )

        items = normalize_question_bank(activity.config_json, default_points=1)
        answers = []
        score = 0
        for item in items:
            field_name = f"match_{item['id']}"
            choice = str(payload.get(field_name, "")).strip()
            is_correct = choice == correct_option(item)["text"]
            if is_correct:
                score += item.get("points", 1)
            answers.append(
                {
                    "item_key": item["id"],
                    "prompt": item["prompt"],
                    "submitted_value": {
                        "choice": choice,
                        "correct_option": correct_option(item)["text"],
                    },
                    "is_correct": is_correct,
                    "score_awarded": item.get("points", 1) if is_correct else 0,
                }
            )

        return TemplateEvaluation(
            score=score,
            max_score=self.get_max_score(activity.config_json),
            is_complete=True,
            answers=answers,
            runtime_state={},
        )
