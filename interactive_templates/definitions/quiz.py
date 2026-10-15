from __future__ import annotations

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


class QuizEditorForm(QuestionBankEditorForm):
    show_result_at_end = forms.BooleanField(required=False, initial=True, label="Показывать результат в конце")
    reveal_correct_answer = forms.BooleanField(
        required=False,
        initial=True,
        label="Показывать правильный ответ сразу после выбора",
    )


def _sample_items() -> list[dict[str, Any]]:
    return sample_question_bank(3, option_count=3)


class QuizDefinition(QuestionBankTemplateDefinition):
    metadata = TemplateMetadata(
        key="quiz",
        title="Викторина",
        description="Классическая викторина с одним правильным ответом.",
        playable=True,
    )
    editor_form_class = QuizEditorForm
    player_template_name = "player/quiz.html"
    preview_template_name = "player/quiz.html"
    editor_question_default_points = DEFAULT_QUESTION_POINTS
    legacy_bulk_actions = {"submit_quiz": "question_{key}"}

    def default_config(self) -> dict[str, Any]:
        return {
            "scoring_enabled": True,
            "show_result_at_end": True,
            "reveal_correct_answer": True,
            "items": _sample_items(),
        }

    def build_editor_initial(self, config: dict[str, Any]) -> dict[str, Any]:
        items = normalize_question_bank(config, default_points=DEFAULT_QUESTION_POINTS)
        return {
            "disable_scoring": not is_scoring_enabled(config),
            "show_result_at_end": config.get("show_result_at_end", True),
            "reveal_correct_answer": config.get("reveal_correct_answer", True),
            "items_json": serialize_question_bank_editor(items, default_points=DEFAULT_QUESTION_POINTS),
            "items_text": serialize_question_bank(items, default_points=DEFAULT_QUESTION_POINTS),
        }

    def build_config(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "scoring_enabled": not cleaned_data.get("disable_scoring", False),
            "show_result_at_end": cleaned_data.get("show_result_at_end", False),
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
        current = next((question for question in questions if not question["is_answered"]), None)
        return {
            "questions": questions,
            # The first unanswered question: a reload continues where the student stopped.
            "current_item_id": current["id"] if current else "",
            "answered_count": sum(1 for question in questions if question["is_answered"]),
            "total_count": len(questions),
            "show_result_at_end": config.get("show_result_at_end", True),
            "reveal_correct_answer": self.reveals_correct_option(config),
            "scoring_enabled": is_scoring_enabled(config),
            "max_score": self.get_max_score(config),
        }
