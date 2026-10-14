from __future__ import annotations

import random
from typing import Any

from django import forms

from interactive_templates.base import QuestionBankTemplateDefinition, TemplateMetadata
from interactive_templates.forms import QuestionBankEditorForm
from interactive_templates.utils import (
    DEFAULT_QUESTION_POINTS,
    build_review_items,
    correct_option,
    get_question_score,
    is_scoring_enabled,
    normalize_answer,
    normalize_question_bank,
    question_bank_items_from_payload,
    serialize_question_bank,
    serialize_question_bank_editor,
)


class MatchingEditorForm(QuestionBankEditorForm):
    shuffle = forms.BooleanField(
        required=False,
        initial=True,
        label="\u041f\u0435\u0440\u0435\u043c\u0435\u0448\u0438\u0432\u0430\u0442\u044c \u043e\u0442\u0432\u0435\u0442\u044b",
    )
    correct_answers_only = forms.BooleanField(
        required=False,
        initial=False,
        label="Показывать только правильные ответы",
        help_text="В общий банк попадут только варианты, отмеченные правильными хотя бы для одного вопроса.",
    )


def _sample_items() -> list[dict[str, Any]]:
    return [
        {
            "id": f"item-{index}",
            "prompt": f"Match prompt {index}",
            "options": [
                {"id": f"item-{index}-option-1", "text": f"Answer {index}", "is_correct": True},
                {"id": f"item-{index}-option-2", "text": f"Wrong {index}", "is_correct": False},
            ],
            "points": DEFAULT_QUESTION_POINTS,
        }
        for index in range(1, 5)
    ]


class MatchingDefinition(QuestionBankTemplateDefinition):
    metadata = TemplateMetadata(
        key="matching",
        title="\u0421\u043e\u043f\u043e\u0441\u0442\u0430\u0432\u043b\u0435\u043d\u0438\u0435",
        description="\u041d\u0443\u0436\u043d\u043e \u0441\u043e\u043f\u043e\u0441\u0442\u0430\u0432\u0438\u0442\u044c \u043a\u0430\u0436\u0434\u044b\u0439 \u0432\u043e\u043f\u0440\u043e\u0441 \u0441 \u043f\u0440\u0430\u0432\u0438\u043b\u044c\u043d\u044b\u043c \u043e\u0442\u0432\u0435\u0442\u043e\u043c.",
        playable=True,
    )
    editor_form_class = MatchingEditorForm
    player_template_name = "player/matching.html"
    preview_template_name = "player/matching.html"
    editor_question_default_points = DEFAULT_QUESTION_POINTS
    legacy_bulk_actions = {"submit_matching": "match_{key}"}

    def default_config(self) -> dict[str, Any]:
        return {
            "scoring_enabled": True,
            "shuffle": True,
            "correct_answers_only": False,
            "items": _sample_items(),
        }

    def build_editor_initial(self, config: dict[str, Any]) -> dict[str, Any]:
        items = normalize_question_bank(config, default_points=DEFAULT_QUESTION_POINTS)
        return {
            "disable_scoring": not is_scoring_enabled(config),
            "shuffle": config.get("shuffle", True),
            "correct_answers_only": config.get("correct_answers_only", False),
            "items_json": serialize_question_bank_editor(items, default_points=DEFAULT_QUESTION_POINTS),
            "items_text": serialize_question_bank(items, default_points=DEFAULT_QUESTION_POINTS),
        }

    def build_config(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "scoring_enabled": not cleaned_data.get("disable_scoring", False),
            "shuffle": cleaned_data.get("shuffle", False),
            "correct_answers_only": cleaned_data.get("correct_answers_only", False),
            "items": question_bank_items_from_payload(
                cleaned_data.get("items_json"),
                cleaned_data.get("items_text", ""),
                default_points=DEFAULT_QUESTION_POINTS,
                previous_items=cleaned_data.get("previous_items"),
            ),
        }

    def answer_bank(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """One card per distinct answer text (case-insensitive), shared by every row, in authoring order."""
        bank: dict[str, dict[str, Any]] = {}
        correct_answers_only = config.get("correct_answers_only", False)
        for item in self.get_items(config):
            for option in item["options"]:
                if correct_answers_only and not option.get("is_correct", False):
                    continue
                normalized_text = normalize_answer(option["text"])
                if not normalized_text or normalized_text in bank:
                    continue
                bank[normalized_text] = {"id": f"matching-choice-{len(bank) + 1}", "text": option["text"]}
        return list(bank.values())

    def option_texts(self, config: dict[str, Any], item: dict[str, Any]) -> list[str]:
        # Every row picks from the same bank of cards.
        return [choice["text"] for choice in self.answer_bank(config)]

    def answers_match(self, choice: str, correct_text: str) -> bool:
        return normalize_answer(choice) == normalize_answer(correct_text)

    def resolve_choice(self, config: dict[str, Any], item: dict[str, Any], choice: str) -> str | None:
        wanted = normalize_answer(choice)
        return next((text for text in self.option_texts(config, item) if normalize_answer(text) == wanted), None)

    def reveals_correct_option(self, config: dict[str, Any]) -> bool:
        # Matching has no reveal setting: the right card is always shown after a wrong pick.
        return True

    def build_answer_feedback(self, config: dict[str, Any], item: dict[str, Any] | None, answer: Any) -> dict[str, Any]:
        feedback = super().build_answer_feedback(config, item, answer)
        feedback["correct_choice_id"] = None
        if item is not None and feedback["correct_option"] is not None:
            # The bank shows each text once, possibly in another letter case than this row's answer.
            wanted = normalize_answer(feedback["correct_option"])
            card = next((card for card in self.answer_bank(config) if normalize_answer(card["text"]) == wanted), None)
            if card:
                feedback["correct_option"] = card["text"]
                feedback["correct_choice_id"] = card["id"]
        return feedback

    def build_runtime_data(
        self,
        activity: Any,
        session: Any | None = None,
        preview: bool = False,
    ) -> dict[str, Any]:
        config = activity.config_json
        items = normalize_question_bank(config, default_points=DEFAULT_QUESTION_POINTS)
        answer_map = {}
        if session:
            answer_map = {answer.item_key: answer for answer in session.answers.all()}

        answer_bank_by_key: dict[str, dict[str, Any]] = {}
        correct_answers_only = config.get("correct_answers_only", False)
        for item in items:
            for option in item["options"]:
                if correct_answers_only and not option.get("is_correct", False):
                    continue
                normalized_text = normalize_answer(option["text"])
                if not normalized_text or normalized_text in answer_bank_by_key:
                    continue
                answer_bank_by_key[normalized_text] = {
                    "id": f"matching-choice-{len(answer_bank_by_key) + 1}",
                    "text": option["text"],
                }
        answer_bank = list(answer_bank_by_key.values())
        seed_base = "preview" if preview else str(session.token) if session else "matching"
        if config.get("shuffle", False):
            random.Random(seed_base).shuffle(answer_bank)

        rows = []
        for item in items:
            answer = answer_map.get(item["id"])
            correct_answer = correct_option(item)
            # Legacy pair configs may hold a blank right side that never reaches the bank.
            bank_choice = answer_bank_by_key.get(
                normalize_answer(correct_answer["text"]),
                {"id": "", "text": correct_answer["text"]},
            )
            rows.append(
                {
                    "id": item["id"],
                    "prompt": item["prompt"],
                    "selected": answer.submitted_value.get("choice", "") if answer else "",
                    "correct_choice_id": bank_choice["id"],
                    "correct_choice_text": bank_choice["text"],
                    "correct_option": bank_choice["text"],
                    "points": get_question_score(config, item),
                }
            )

        return {
            "rows": rows,
            "answer_bank": answer_bank,
            "choices": [choice["text"] for choice in answer_bank],
            "reveal_correct_answer": True,
            "scoring_enabled": is_scoring_enabled(config),
            "max_score": self.get_max_score(config),
            "review_items": build_review_items(items, answer_map, config=config),
        }
