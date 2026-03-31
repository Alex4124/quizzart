from __future__ import annotations

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


class ChooseABoxEditorForm(forms.Form):
    no_repeat = forms.BooleanField(
        required=False,
        initial=True,
        label="Не разрешать повторное открытие коробок",
    )
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
            "prompt": f"Sample prompt {index}",
            "options": [
                {"id": f"item-{index}-option-1", "text": f"Correct {index}", "is_correct": True},
                {"id": f"item-{index}-option-2", "text": f"Wrong A{index}", "is_correct": False},
                {"id": f"item-{index}-option-3", "text": f"Wrong B{index}", "is_correct": False},
            ],
            "points": index * 100,
        }
        for index in range(1, 7)
    ]


class ChooseABoxDefinition(BaseTemplateDefinition):
    metadata = TemplateMetadata(
        key="choose_a_box",
        title="Выбери коробку",
        description="Ученик открывает коробку, видит вопрос и отвечает на него.",
        playable=True,
    )
    editor_form_class = ChooseABoxEditorForm
    player_template_name = "player/choose_a_box.html"
    preview_template_name = "player/choose_a_box.html"
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
        config = activity.config_json
        items = normalize_question_bank(config, default_points=100)
        answers_by_key = {}
        opened_keys = set()
        if session:
            answers_by_key = {answer.item_key: answer for answer in session.answers.all()}
            opened_keys = set(session.runtime_state.get("opened", []))

        boxes = []
        for index, item in enumerate(items, start=1):
            answer = answers_by_key.get(item["id"])
            if answer:
                state = "answered"
            elif item["id"] in opened_keys:
                state = "opened"
            else:
                state = "preview" if preview else "unopened"
            boxes.append(
                {
                    "id": item["id"],
                    "number": index,
                    "prompt": item["prompt"],
                    "options": choice_texts(item),
                    "points": item.get("points", 0),
                    "state": state,
                    "submitted_answer": answer.submitted_value.get("choice", "") if answer else "",
                    "expected_answer": correct_option(item)["text"],
                    "is_correct": answer.is_correct if answer else None,
                }
            )

        return {
            "boxes": boxes,
            "no_repeat": config.get("no_repeat", False),
            "reveal_correct_answer": config.get("reveal_correct_answer", True),
            "answered_count": len(answers_by_key),
            "total_boxes": len(items),
            "max_score": self.get_max_score(config),
            "show_finish": not preview and (answers_by_key or opened_keys),
            "review_items": build_review_items(items, answers_by_key),
        }

    def get_max_score(self, config: dict[str, Any]) -> int:
        items = normalize_question_bank(config, default_points=100)
        return sum(item.get("points", 0) for item in items)

    def evaluate_submission(
        self,
        activity: Any,
        session: Any,
        payload: dict[str, Any],
    ) -> TemplateEvaluation:
        items = {item["id"]: item for item in normalize_question_bank(activity.config_json, default_points=100)}
        existing_answers = {answer.item_key: answer for answer in session.answers.all()}
        opened = list(session.runtime_state.get("opened", []))
        score = sum(answer.score_awarded for answer in existing_answers.values())
        max_score = self.get_max_score(activity.config_json)
        action = payload.get("action")

        if action == "open_box":
            item_key = payload.get("item_key", "")
            if item_key in items and item_key not in opened and item_key not in existing_answers:
                opened.append(item_key)
            return TemplateEvaluation(
                score=score,
                max_score=max_score,
                is_complete=False,
                runtime_state={"opened": opened},
            )

        if action == "answer_box":
            item_key = payload.get("item_key", "")
            selected_choice = str(payload.get("answer", "")).strip()
            if item_key not in items:
                raise ValidationError("Выбрана неизвестная коробка.")
            if item_key not in opened:
                opened.append(item_key)
            if item_key in existing_answers:
                return TemplateEvaluation(
                    score=score,
                    max_score=max_score,
                    is_complete=len(existing_answers) >= len(items),
                    runtime_state={"opened": opened},
                )

            item = items[item_key]
            is_correct = selected_choice == correct_option(item)["text"]
            score_awarded = item["points"] if is_correct else 0
            score += score_awarded
            answered_total = len(existing_answers) + 1
            return TemplateEvaluation(
                score=score,
                max_score=max_score,
                is_complete=answered_total >= len(items),
                runtime_state={"opened": opened},
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
            answers = []
            score = 0
            opened = list(opened)

            for item_key, item in items.items():
                existing_answer = existing_answers.get(item_key)
                selected_choice = str(payload.get(f"box_{item_key}", "")).strip()

                if existing_answer:
                    answers.append(
                        {
                            "item_key": item_key,
                            "prompt": existing_answer.prompt or item["prompt"],
                            "submitted_value": existing_answer.submitted_value,
                            "is_correct": existing_answer.is_correct,
                            "score_awarded": existing_answer.score_awarded,
                        }
                    )
                    score += existing_answer.score_awarded
                    if item_key not in opened:
                        opened.append(item_key)
                    continue

                if not selected_choice:
                    continue

                is_correct = selected_choice == correct_option(item)["text"]
                score_awarded = item["points"] if is_correct else 0
                score += score_awarded
                if item_key not in opened:
                    opened.append(item_key)
                answers.append(
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
                )

            return TemplateEvaluation(
                score=score,
                max_score=max_score,
                is_complete=True,
                runtime_state={"opened": opened},
                answers=answers,
            )

        raise ValidationError("Неизвестное действие для шаблона 'Выбери коробку'.")
