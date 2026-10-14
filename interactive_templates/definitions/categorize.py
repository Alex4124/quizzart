from __future__ import annotations

import random
from typing import Any

from django import forms

from interactive_templates.base import QuestionBankTemplateDefinition, TemplateMetadata
from interactive_templates.forms import QuestionBankEditorForm
from interactive_templates.utils import (
    DEFAULT_QUESTION_POINTS,
    is_scoring_enabled,
    normalize_question_bank,
    question_bank_items_from_payload,
    serialize_question_bank,
    serialize_question_bank_editor,
)


class CategorizeEditorForm(QuestionBankEditorForm):
    shuffle = forms.BooleanField(required=False, initial=True, label="Перемешивать порядок карточек")
    reveal_correct_answer = forms.BooleanField(
        required=False,
        initial=True,
        label="Показывать правильный ответ сразу после выбора",
    )


def _sample_items() -> list[dict[str, Any]]:
    return [
        {
            "id": f"item-{index}",
            "prompt": f"Вопрос на карточке {index}",
            "options": [
                {"id": f"item-{index}-option-1", "text": f"Правильный ответ {index}", "is_correct": True},
                {"id": f"item-{index}-option-2", "text": f"Неверный ответ {index}", "is_correct": False},
            ],
            "points": DEFAULT_QUESTION_POINTS,
        }
        for index in range(1, 5)
    ]


class CategorizeDefinition(QuestionBankTemplateDefinition):
    metadata = TemplateMetadata(
        key="categorize",
        title="Карточки",
        description="Откройте карточку, выберите правильный ответ и постепенно пройдите весь набор вопросов.",
        playable=True,
    )
    editor_form_class = CategorizeEditorForm
    player_template_name = "player/categorize.html"
    preview_template_name = "player/categorize.html"
    editor_question_default_points = DEFAULT_QUESTION_POINTS
    legacy_bulk_actions = {"submit_categorize": "question_{key}"}

    def default_config(self) -> dict[str, Any]:
        return {
            "scoring_enabled": True,
            "shuffle": True,
            "reveal_correct_answer": True,
            "items": _sample_items(),
        }

    def build_editor_initial(self, config: dict[str, Any]) -> dict[str, Any]:
        items = normalize_question_bank(config, default_points=DEFAULT_QUESTION_POINTS)
        return {
            "disable_scoring": not is_scoring_enabled(config),
            "shuffle": config.get("shuffle", True),
            "reveal_correct_answer": config.get("reveal_correct_answer", True),
            "items_json": serialize_question_bank_editor(items, default_points=DEFAULT_QUESTION_POINTS),
            "items_text": serialize_question_bank(items, default_points=DEFAULT_QUESTION_POINTS),
        }

    def build_config(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "scoring_enabled": not cleaned_data.get("disable_scoring", False),
            "shuffle": cleaned_data.get("shuffle", False),
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
        # No answer key here: answered cards carry only the feedback the reveal setting allows.
        cards = self.build_item_states(activity, session, preview=preview)
        if config.get("shuffle", False):
            # Seeded per run, so a reload keeps the cards where the student saw them.
            seed_base = "preview" if preview else str(session.token) if session else "categorize"
            random.Random(seed_base).shuffle(cards)
        for position, card in enumerate(cards, start=1):
            card["number"] = position

        return {
            "cards": cards,
            "answered_count": sum(1 for card in cards if card["is_answered"]),
            "total_count": len(cards),
            "reveal_correct_answer": self.reveals_correct_option(config),
            "scoring_enabled": is_scoring_enabled(config),
            "max_score": self.get_max_score(config),
        }

    def reveals_correctness(self, config: dict[str, Any]) -> bool:
        # With the reveal setting off, cards only say «Ответ сохранён» until the results page.
        return bool(config.get("reveal_correct_answer", True))
