from __future__ import annotations

from typing import Any

from django import forms

from interactive_templates.base import QuestionBankTemplateDefinition, TemplateEvaluation, TemplateMetadata
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


class ChooseABoxEditorForm(QuestionBankEditorForm):
    reveal_correct_answer = forms.BooleanField(
        required=False,
        initial=True,
        label="Показывать правильный ответ сразу после выбора",
    )


def _sample_items() -> list[dict[str, Any]]:
    return sample_question_bank(6, option_count=3)


def _box_state(box: dict[str, Any], opened_keys: set[str]) -> str:
    if box["is_answered"]:
        return "answered"
    return "opened" if box["id"] in opened_keys else "unopened"


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
    allows_early_finish = True
    review_item_label = "Коробка"

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
        # Opened boxes are kept on the server, so a reload shows the same board; the preview opens them in the page.
        opened_keys = set((session.runtime_state or {}).get("opened", [])) if session else set()
        boxes = [
            {**box, "state": _box_state(box, opened_keys)}
            for box in self.build_item_states(activity, session, preview=preview)
        ]
        answered_count = sum(1 for box in boxes if box["is_answered"])
        return {
            "boxes": boxes,
            "answered_count": answered_count,
            "total_count": len(boxes),
            "reveal_correct_answer": self.reveals_correct_option(config),
            "scoring_enabled": is_scoring_enabled(config),
            "max_score": self.get_max_score(config),
            # Finishing early makes sense once something is answered; the preview has nothing to finish.
            "show_finish": not preview and answered_count > 0,
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
