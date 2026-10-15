from __future__ import annotations

import math
import random
from typing import Any

from django import forms

from interactive_templates.base import QuestionBankTemplateDefinition, TemplateMetadata
from interactive_templates.forms import QuestionBankEditorForm
from interactive_templates.utils import (
    sample_question_bank,
    DEFAULT_QUESTION_POINTS,
    is_scoring_enabled,
    normalize_question_bank,
    question_bank_items_from_payload,
    serialize_question_bank,
    serialize_question_bank_editor,
)


class SnakeEditorForm(QuestionBankEditorForm):
    reveal_correct_answer = forms.BooleanField(
        required=False,
        initial=True,
        label="Показывать правильный ответ сразу после выбора",
    )


def _sample_items() -> list[dict[str, Any]]:
    return sample_question_bank(4, option_count=3)


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


class SnakeDefinition(QuestionBankTemplateDefinition):
    metadata = TemplateMetadata(
        key="snake",
        title="Змейка",
        description="Ведите змейку стрелками или кнопками, собирайте яблоки и отвечайте на вопросы.",
        playable=True,
    )
    editor_form_class = SnakeEditorForm
    player_template_name = "player/snake.html"
    preview_template_name = "player/snake.html"
    editor_question_default_points = DEFAULT_QUESTION_POINTS
    legacy_bulk_actions = {"submit_snake": "question_{key}"}
    legacy_bulk_requires_all = True
    review_item_label = "Яблоко"

    def default_config(self) -> dict[str, Any]:
        return {
            "scoring_enabled": True,
            "reveal_correct_answer": True,
            "items": _sample_items(),
        }

    def build_editor_initial(self, config: dict[str, Any]) -> dict[str, Any]:
        items = normalize_question_bank(config, default_points=DEFAULT_QUESTION_POINTS)
        return {
            "disable_scoring": not is_scoring_enabled(config),
            "reveal_correct_answer": config.get("reveal_correct_answer", True),
            "items_json": serialize_question_bank_editor(items, default_points=DEFAULT_QUESTION_POINTS),
            "items_text": serialize_question_bank(items, default_points=DEFAULT_QUESTION_POINTS),
        }

    def build_config(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "scoring_enabled": not cleaned_data.get("disable_scoring", False),
            "reveal_correct_answer": cleaned_data.get("reveal_correct_answer", False),
            "items": question_bank_items_from_payload(
                cleaned_data.get("items_json"),
                cleaned_data.get("items_text", ""),
                default_points=DEFAULT_QUESTION_POINTS,
                previous_items=cleaned_data.get("previous_items"),
            ),
        }

    def build_runtime_data(
        self,
        activity: Any,
        session: Any | None = None,
        preview: bool = False,
    ) -> dict[str, Any]:
        config = activity.config_json
        questions = self.build_item_states(activity, session, preview=preview)
        seed_base = "preview" if preview else str(session.token) if session else "snake"
        positions = _build_apple_positions(len(questions), seed_base)
        # An answered apple is already eaten: a reload keeps the snake's length and only the rest stay on the board.
        apples = [
            {**question, "x_percent": x_percent, "y_percent": y_percent}
            for question, (x_percent, y_percent) in zip(questions, positions)
        ]
        return {
            "apples": apples,
            "answered_count": sum(1 for apple in apples if apple["is_answered"]),
            "total_count": len(apples),
            "reveal_correct_answer": self.reveals_correct_option(config),
            "scoring_enabled": is_scoring_enabled(config),
            "max_score": self.get_max_score(config),
        }
