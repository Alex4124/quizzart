from __future__ import annotations

import random
from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from interactive_templates.base import BaseTemplateDefinition, TemplateEvaluation, TemplateMetadata
from interactive_templates.forms import QuestionBankEditorForm
from interactive_templates.utils import (
    DEFAULT_QUESTION_POINTS,
    build_review_items,
    correct_option,
    get_question_bank_max_score,
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
    editor_question_default_points = DEFAULT_QUESTION_POINTS

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
            ),
        }

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
            bank_choice = answer_bank_by_key[normalize_answer(correct_answer["text"])]
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

    def get_max_score(self, config: dict[str, Any]) -> int:
        return get_question_bank_max_score(config)

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

        config = activity.config_json
        items = normalize_question_bank(config, default_points=DEFAULT_QUESTION_POINTS)
        answers = []
        score = 0
        for item in items:
            field_name = f"match_{item['id']}"
            choice = str(payload.get(field_name, "")).strip()
            is_correct = normalize_answer(choice) == normalize_answer(correct_option(item)["text"])
            awarded_points = get_question_score(config, item) if is_correct else 0
            if is_correct:
                score += awarded_points
            answers.append(
                {
                    "item_key": item["id"],
                    "prompt": item["prompt"],
                    "submitted_value": {
                        "choice": choice,
                        "correct_option": correct_option(item)["text"],
                    },
                    "is_correct": is_correct,
                    "score_awarded": awarded_points,
                }
            )

        return TemplateEvaluation(
            score=score,
            max_score=self.get_max_score(activity.config_json),
            is_complete=True,
            answers=answers,
            runtime_state={},
        )
