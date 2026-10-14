from __future__ import annotations

from typing import Any

from django import forms

from interactive_templates.base import QuestionBankTemplateDefinition, TemplateEvaluation, TemplateMetadata
from interactive_templates.forms import QuestionBankEditorForm
from interactive_templates.utils import (
    DEFAULT_QUESTION_POINTS,
    build_review_items,
    choice_texts,
    correct_option,
    get_question_score,
    is_scoring_enabled,
    normalize_question_bank,
    question_bank_items_from_payload,
    serialize_question_bank,
    serialize_question_bank_editor,
)


class ChooseABoxEditorForm(QuestionBankEditorForm):
    reveal_correct_answer = forms.BooleanField(
        required=False,
        initial=True,
        label="Показывать правильный ответ сразу после выбора",
    )


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
            "points": DEFAULT_QUESTION_POINTS,
        }
        for index in range(1, 7)
    ]


class ChooseABoxDefinition(QuestionBankTemplateDefinition):
    metadata = TemplateMetadata(
        key="choose_a_box",
        title="Выбери коробку",
        description="Ученик открывает коробку, видит вопрос и отвечает на него.",
        playable=True,
    )
    editor_form_class = ChooseABoxEditorForm
    player_template_name = "player/choose_a_box.html"
    preview_template_name = "player/choose_a_box.html"
    editor_question_default_points = DEFAULT_QUESTION_POINTS
    answer_actions = frozenset({"answer", "answer_box"})
    # "finish" with box_<id> fields is how pages loaded before per-answer checks ended a run.
    legacy_bulk_actions = {"finish": "box_{key}"}
    allows_early_finish = True

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
        items = normalize_question_bank(config, default_points=DEFAULT_QUESTION_POINTS)
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
                    "points": get_question_score(config, item),
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
            "scoring_enabled": is_scoring_enabled(config),
            "answered_count": len(answers_by_key),
            "total_boxes": len(items),
            "max_score": self.get_max_score(config),
            "show_finish": not preview and (answers_by_key or opened_keys),
            "review_items": build_review_items(items, answers_by_key, config=config),
        }

    @staticmethod
    def _with_opened(session: Any, item_key: str) -> dict[str, Any]:
        opened = list(session.runtime_state.get("opened", []))
        if item_key not in opened:
            opened.append(item_key)
        return {**session.runtime_state, "opened": opened}

    def after_answer_state(self, session: Any, item_key: str) -> dict[str, Any] | None:
        return self._with_opened(session, item_key)

    def handle_custom_action(self, activity: Any, session: Any, action: str, payload: Any) -> TemplateEvaluation | None:
        if action != "open_box":
            return None
        item = self.get_item(activity.config_json, str(payload.get("item_key", "")).strip())
        return TemplateEvaluation(runtime_state=self._with_opened(session, item["id"]), item_key=item["id"])
