from __future__ import annotations

import random
from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from interactive_templates.base import (
    BaseTemplateDefinition,
    TemplateEvaluation,
    TemplateMetadata,
)
from interactive_templates.utils import (
    build_review_items,
    choice_texts,
    correct_option,
    normalize_question_bank,
    question_bank_items_from_payload,
    serialize_question_bank,
    serialize_question_bank_editor,
)


class QuizEditorForm(forms.Form):
    show_result_at_end = forms.BooleanField(required=False, initial=True, label="Показывать результат в конце")
    reveal_correct_answer = forms.BooleanField(
        required=False,
        initial=True,
        label="Показывать правильный ответ сразу после выбора",
    )
    items_json = forms.CharField(required=False, widget=forms.HiddenInput())
    items_text = forms.CharField(required=False, widget=forms.HiddenInput())


def _sample_items() -> list[dict[str, Any]]:
    return [
        {
            "id": f"item-{index}",
            "prompt": f"Sample question {index}?",
            "options": [
                {"id": f"item-{index}-option-1", "text": f"Correct {index}", "is_correct": True},
                {"id": f"item-{index}-option-2", "text": f"Wrong A{index}", "is_correct": False},
                {"id": f"item-{index}-option-3", "text": f"Wrong B{index}", "is_correct": False},
            ],
            "points": 1,
        }
        for index in range(1, 4)
    ]


class QuizDefinition(BaseTemplateDefinition):
    metadata = TemplateMetadata(
        key="quiz",
        title="Викторина",
        description="Классическая викторина с одним правильным ответом.",
        playable=True,
    )
    editor_form_class = QuizEditorForm
    player_template_name = "player/quiz.html"
    preview_template_name = "player/quiz.html"
    editor_question_default_points = 1

    def default_config(self) -> dict[str, Any]:
        return {
            "show_result_at_end": True,
            "reveal_correct_answer": True,
            "items": _sample_items(),
        }

    def build_editor_initial(self, config: dict[str, Any]) -> dict[str, Any]:
        items = normalize_question_bank(config, default_points=1)
        return {
            "show_result_at_end": config.get("show_result_at_end", True),
            "reveal_correct_answer": config.get("reveal_correct_answer", True),
            "items_json": serialize_question_bank_editor(items, default_points=1),
            "items_text": serialize_question_bank(items, default_points=1),
        }

    def build_config(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "show_result_at_end": cleaned_data.get("show_result_at_end", False),
            "reveal_correct_answer": cleaned_data.get("reveal_correct_answer", False),
            "items": question_bank_items_from_payload(
                cleaned_data.get("items_json"),
                cleaned_data.get("items_text", ""),
                default_points=1,
            ),
        }

    def build_runtime_data(
        self,
        activity: Any,
        session: Any | None = None,
        preview: bool = False,
    ) -> dict[str, Any]:
        items = normalize_question_bank(activity.config_json, default_points=1)
        answer_map = {}
        seed_base = "preview" if preview else str(session.token) if session else "anonymous"
        if session:
            answer_map = {answer.item_key: answer for answer in session.answers.all()}

        questions = []
        for index, item in enumerate(items, start=1):
            shuffled = list(choice_texts(item))
            random.Random(f"{seed_base}-{index}").shuffle(shuffled)
            answer = answer_map.get(item["id"])
            questions.append(
                {
                    "id": item["id"],
                    "prompt": item["prompt"],
                    "options": shuffled,
                    "selected_option": answer.submitted_value.get("choice") if answer else "",
                    "correct_option": correct_option(item)["text"],
                    "is_correct": answer.is_correct if answer else None,
                    "points": item.get("points", 1),
                }
            )

        return {
            "questions": questions,
            "show_result_at_end": activity.config_json.get("show_result_at_end", True),
            "reveal_correct_answer": activity.config_json.get("reveal_correct_answer", True),
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
        if payload.get("action") != "submit_quiz":
            raise ValidationError("Неизвестное действие для шаблона 'Викторина'.")

        items = normalize_question_bank(activity.config_json, default_points=1)
        answers = []
        score = 0
        max_score = self.get_max_score(activity.config_json)

        for item in items:
            field_name = f"question_{item['id']}"
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
            max_score=max_score,
            is_complete=True,
            answers=answers,
            runtime_state={},
        )
