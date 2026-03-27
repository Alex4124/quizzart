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


class CategorizeEditorForm(forms.Form):
    shuffle = forms.BooleanField(required=False, initial=True, label="Перемешивать порядок карточек")
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
            "prompt": f"Вопрос на карточке {index}",
            "options": [
                {"id": f"item-{index}-option-1", "text": f"Правильный ответ {index}", "is_correct": True},
                {"id": f"item-{index}-option-2", "text": f"Неверный ответ {index}", "is_correct": False},
            ],
            "points": 1,
        }
        for index in range(1, 5)
    ]


class CategorizeDefinition(BaseTemplateDefinition):
    metadata = TemplateMetadata(
        key="categorize",
        title="Карточки",
        description="Откройте карточку, выберите правильный ответ и постепенно пройдите весь набор вопросов.",
        playable=True,
    )
    editor_form_class = CategorizeEditorForm
    player_template_name = "player/categorize.html"
    preview_template_name = "player/categorize.html"
    editor_question_default_points = 1

    def default_config(self) -> dict[str, Any]:
        return {
            "shuffle": True,
            "reveal_correct_answer": True,
            "items": _sample_items(),
        }

    def build_editor_initial(self, config: dict[str, Any]) -> dict[str, Any]:
        items = normalize_question_bank(config, default_points=1)
        return {
            "shuffle": config.get("shuffle", True),
            "reveal_correct_answer": config.get("reveal_correct_answer", True),
            "items_json": serialize_question_bank_editor(items, default_points=1),
            "items_text": serialize_question_bank(items, default_points=1),
        }

    def build_config(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "shuffle": cleaned_data.get("shuffle", False),
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
        if session:
            answer_map = {answer.item_key: answer for answer in session.answers.all()}

        seed_base = "preview" if preview else str(session.token) if session else "categorize"
        cards = []
        for item in items:
            answer = answer_map.get(item["id"])
            selected_value = ""
            if answer:
                selected_value = answer.submitted_value.get("choice", answer.submitted_value.get("answer", ""))
            cards.append(
                {
                    "id": item["id"],
                    "prompt": item["prompt"],
                    "options": [
                        {
                            "id": option["id"],
                            "text": option["text"],
                            "is_correct": option["is_correct"],
                        }
                        for option in item.get("options", [])
                    ],
                    "selected": selected_value,
                    "is_answered": bool(answer),
                    "correct_option": correct_option(item)["text"],
                    "points": item.get("points", 1),
                }
            )

        if activity.config_json.get("shuffle", False):
            random.Random(seed_base).shuffle(cards)

        return {
            "cards": cards,
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
        if payload.get("action") != "submit_categorize":
            raise ValidationError("Неизвестное действие для шаблона 'Карточки'.")

        items = normalize_question_bank(activity.config_json, default_points=1)
        answers = []
        score = 0
        for item in items:
            question_field = f"question_{item['id']}"
            legacy_field = f"category_{item['id']}"
            choice = str(payload.get(question_field, payload.get(legacy_field, ""))).strip()
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
