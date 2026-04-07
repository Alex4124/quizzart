from __future__ import annotations

import random
from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from interactive_templates.base import BaseTemplateDefinition, TemplateEvaluation, TemplateMetadata
from interactive_templates.utils import (
    build_review_items,
    choice_texts,
    correct_option,
    normalize_question_bank,
    question_bank_items_from_payload,
    serialize_question_bank,
    serialize_question_bank_editor,
)


class WheelEditorForm(forms.Form):
    no_repeat = forms.BooleanField(required=False, initial=True, label="Не повторять уже выпавшие вопросы")
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
            "prompt": f"Wheel prompt {index}",
            "options": [
                {"id": f"item-{index}-option-1", "text": f"Correct {index}", "is_correct": True},
                {"id": f"item-{index}-option-2", "text": f"Wrong A{index}", "is_correct": False},
                {"id": f"item-{index}-option-3", "text": f"Wrong B{index}", "is_correct": False},
            ],
            "points": index * 100,
        }
        for index in range(1, 6)
    ]


def _wheel_sector_fills(count: int) -> list[str]:
    palette = ["#c11755", "#aa7af1", "#ff9368", "#7d44c8", "#62bdf5"]
    if count <= 0:
        return []
    if len(palette) == 1:
        return palette * count

    period = (len(palette) * 2) - 2
    fills: list[str] = []
    for index in range(count):
        palette_index = index % period
        if palette_index >= len(palette):
            palette_index = period - palette_index
        fills.append(palette[palette_index])
    return fills


class WheelOfFortuneDefinition(BaseTemplateDefinition):
    metadata = TemplateMetadata(
        key="wheel_of_fortune",
        title="Колесо фортуны",
        description="Запуск вращения, остановка на секторе и ответ на выпавший вопрос.",
        playable=True,
    )
    editor_form_class = WheelEditorForm
    player_template_name = "player/wheel_of_fortune.html"
    preview_template_name = "player/wheel_of_fortune.html"
    editor_question_default_points = 100

    def default_config(self) -> dict[str, Any]:
        return {
            "no_repeat": True,
            "reveal_correct_answer": True,
            "items": _sample_items(),
        }

    def build_editor_initial(self, config: dict[str, Any]) -> dict[str, Any]:
        items = normalize_question_bank(config, default_points=100)
        return {
            "no_repeat": config.get("no_repeat", True),
            "reveal_correct_answer": config.get("reveal_correct_answer", True),
            "items_json": serialize_question_bank_editor(items, default_points=100),
            "items_text": serialize_question_bank(items, default_points=100),
        }

    def build_config(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "no_repeat": cleaned_data.get("no_repeat", False),
            "reveal_correct_answer": cleaned_data.get("reveal_correct_answer", False),
            "items": question_bank_items_from_payload(
                cleaned_data.get("items_json"),
                cleaned_data.get("items_text", ""),
                default_points=100,
            ),
        }

    def build_runtime_data(
        self,
        activity: Any,
        session: Any | None = None,
        preview: bool = False,
    ) -> dict[str, Any]:
        items = normalize_question_bank(activity.config_json, default_points=100)
        answers_by_key = {}
        active_item_id = ""
        if session:
            answers_by_key = {answer.item_key: answer for answer in session.answers.all()}
            active_item_id = session.runtime_state.get("active_item", "")

        active_item = next((item for item in items if item["id"] == active_item_id), None)
        sectors = []
        fills = _wheel_sector_fills(len(items))
        for index, item in enumerate(items, start=1):
            sectors.append(
                {
                    "id": item["id"],
                    "label": item.get("points", index * 100),
                    "prompt": item["prompt"],
                    "options": choice_texts(item),
                    "correct_option": correct_option(item)["text"],
                    "points": item.get("points", 100),
                    "is_active": item["id"] == active_item_id,
                    "is_answered": item["id"] in answers_by_key,
                    "fill": fills[index - 1],
                }
            )

        return {
            "sectors": sectors,
            "active_item": {
                "id": active_item["id"],
                "prompt": active_item["prompt"],
                "options": choice_texts(active_item),
                "correct_option": correct_option(active_item)["text"],
                "points": active_item.get("points", 100),
            }
            if active_item
            else None,
            "answered_count": len(answers_by_key),
            "total_items": len(items),
            "max_score": self.get_max_score(activity.config_json),
            "review_items": build_review_items(items, answers_by_key),
            "preview": preview,
            "no_repeat": activity.config_json.get("no_repeat", False),
            "reveal_correct_answer": activity.config_json.get("reveal_correct_answer", True),
        }

    def get_max_score(self, config: dict[str, Any]) -> int:
        items = normalize_question_bank(config, default_points=100)
        return sum(item.get("points", 100) for item in items)

    def evaluate_submission(
        self,
        activity: Any,
        session: Any,
        payload: dict[str, Any],
    ) -> TemplateEvaluation:
        items = normalize_question_bank(activity.config_json, default_points=100)
        items_by_id = {item["id"]: item for item in items}
        existing_answers = {answer.item_key: answer for answer in session.answers.all()}
        score = sum(answer.score_awarded for answer in existing_answers.values())
        max_score = self.get_max_score(activity.config_json)
        runtime_state = dict(session.runtime_state)
        action = payload.get("action")

        if action == "spin_wheel":
            available_items = [item for item in items if item["id"] not in existing_answers]
            if not available_items:
                return TemplateEvaluation(
                    score=score,
                    max_score=max_score,
                    is_complete=True,
                    runtime_state=runtime_state,
                )
            chosen_item = random.choice(available_items)
            runtime_state["active_item"] = chosen_item["id"]
            return TemplateEvaluation(
                score=score,
                max_score=max_score,
                is_complete=False,
                runtime_state=runtime_state,
            )

        if action == "answer_wheel":
            item_key = runtime_state.get("active_item") or payload.get("item_key", "")
            selected_choice = str(payload.get("answer", "")).strip()
            if item_key not in items_by_id:
                raise ValidationError("Сначала раскрутите колесо.")
            if item_key in existing_answers:
                return TemplateEvaluation(
                    score=score,
                    max_score=max_score,
                    is_complete=len(existing_answers) >= len(items),
                    runtime_state=runtime_state,
                )

            item = items_by_id[item_key]
            is_correct = selected_choice == correct_option(item)["text"]
            score_awarded = item.get("points", 100) if is_correct else 0
            runtime_state["active_item"] = ""
            answered_total = len(existing_answers) + 1
            return TemplateEvaluation(
                score=score + score_awarded,
                max_score=max_score,
                is_complete=answered_total >= len(items),
                runtime_state=runtime_state,
                answers=[
                    {
                        "item_key": item_key,
                        "prompt": item["prompt"],
                        "submitted_value": {
                            "choice": selected_choice,
                            "correct_option": correct_option(item)["text"],
                        },
                        "is_correct": is_correct,
                        "score_awarded": score_awarded,
                    }
                ],
            )

        if action == "finish":
            return TemplateEvaluation(
                score=score,
                max_score=max_score,
                is_complete=True,
                runtime_state=runtime_state,
            )

        raise ValidationError("Неизвестное действие для шаблона 'Колесо фортуны'.")
