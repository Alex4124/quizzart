from __future__ import annotations

import math
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


class SnakeEditorForm(forms.Form):
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
            "prompt": f"Snake question {index}",
            "options": [
                {"id": f"item-{index}-option-1", "text": f"Correct {index}", "is_correct": True},
                {"id": f"item-{index}-option-2", "text": f"Wrong A{index}", "is_correct": False},
                {"id": f"item-{index}-option-3", "text": f"Wrong B{index}", "is_correct": False},
            ],
            "points": 1,
        }
        for index in range(1, 5)
    ]


def _distance(first: tuple[float, float], second: tuple[float, float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _grid_scatter_positions(count: int, rng: random.Random) -> list[tuple[float, float]]:
    if count <= 0:
        return []

    columns = max(2, math.ceil(math.sqrt(count)))
    rows = math.ceil(count / columns)
    slots = [(column, row) for row in range(rows) for column in range(columns)]
    rng.shuffle(slots)

    positions: list[tuple[float, float]] = []
    for column, row in slots[:count]:
        x = 16.0 if columns == 1 else 16.0 + (68.0 * column / max(columns - 1, 1))
        y = 18.0 if rows == 1 else 18.0 + (60.0 * row / max(rows - 1, 1))
        if _distance((x, y), (50.0, 50.0)) < 14.0:
            y = min(82.0, y + 18.0)
        positions.append((round(x, 2), round(y, 2)))
    return positions


def _build_apple_positions(count: int, seed: str) -> list[tuple[float, float]]:
    if count <= 0:
        return []

    rng = random.Random(seed)
    positions: list[tuple[float, float]] = []
    min_distance = 16.0 if count <= 8 else 13.0

    for _ in range(count):
        placed = False
        for _attempt in range(96):
            candidate = (rng.uniform(12.0, 88.0), rng.uniform(18.0, 82.0))
            if _distance(candidate, (50.0, 50.0)) < 12.0:
                continue
            if any(_distance(candidate, existing) < min_distance for existing in positions):
                continue
            positions.append((round(candidate[0], 2), round(candidate[1], 2)))
            placed = True
            break
        if not placed:
            return _grid_scatter_positions(count, rng)

    return positions


class SnakeDefinition(BaseTemplateDefinition):
    metadata = TemplateMetadata(
        key="snake",
        title="Змейка",
        description="Змейка следует за курсором или пальцем, ест яблоки и открывает вопросы.",
        playable=True,
    )
    editor_form_class = SnakeEditorForm
    player_template_name = "player/snake.html"
    preview_template_name = "player/snake.html"
    editor_question_default_points = 1

    def default_config(self) -> dict[str, Any]:
        return {
            "reveal_correct_answer": True,
            "items": _sample_items(),
        }

    def build_editor_initial(self, config: dict[str, Any]) -> dict[str, Any]:
        items = normalize_question_bank(config, default_points=1)
        return {
            "reveal_correct_answer": config.get("reveal_correct_answer", True),
            "items_json": serialize_question_bank_editor(items, default_points=1),
            "items_text": serialize_question_bank(items, default_points=1),
        }

    def build_config(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        return {
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

        seed_base = "preview" if preview else str(session.token) if session else "snake"
        positions = _build_apple_positions(len(items), seed_base)
        apples = []
        for index, item in enumerate(items, start=1):
            answer = answer_map.get(item["id"])
            shuffled_options = list(choice_texts(item))
            random.Random(f"{seed_base}-item-{index}").shuffle(shuffled_options)
            apples.append(
                {
                    "id": item["id"],
                    "number": index,
                    "prompt": item["prompt"],
                    "options": shuffled_options,
                    "correct_option": correct_option(item)["text"],
                    "selected_option": answer.submitted_value.get("choice", "") if answer else "",
                    "is_correct": answer.is_correct if answer else None,
                    "points": item.get("points", 1),
                    "x_percent": positions[index - 1][0],
                    "y_percent": positions[index - 1][1],
                }
            )

        return {
            "apples": apples,
            "answered_count": len(answer_map),
            "total_items": len(items),
            "max_score": self.get_max_score(activity.config_json),
            "reveal_correct_answer": activity.config_json.get("reveal_correct_answer", True),
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
        if payload.get("action") != "submit_snake":
            raise ValidationError("Неизвестное действие для шаблона 'Змейка'.")

        items = normalize_question_bank(activity.config_json, default_points=1)
        answers = []
        score = 0
        missing_answers = False

        for item in items:
            field_name = f"question_{item['id']}"
            choice = str(payload.get(field_name, "")).strip()
            if not choice:
                missing_answers = True
                continue

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

        if missing_answers or len(answers) != len(items):
            raise ValidationError("Сначала ответьте на все вопросы, чтобы завершить змейку.")

        return TemplateEvaluation(
            score=score,
            max_score=self.get_max_score(activity.config_json),
            is_complete=True,
            answers=answers,
            runtime_state={},
        )
