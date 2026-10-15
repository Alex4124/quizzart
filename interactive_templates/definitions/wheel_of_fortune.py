from __future__ import annotations

import random
from typing import Any

from django import forms
from django.core.exceptions import ValidationError

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


class WheelEditorForm(QuestionBankEditorForm):
    no_repeat = forms.BooleanField(required=False, initial=True, label="Не повторять уже выпавшие вопросы")
    reveal_correct_answer = forms.BooleanField(
        required=False,
        initial=True,
        label="Показывать правильный ответ сразу после выбора",
    )


def _sample_items() -> list[dict[str, Any]]:
    return sample_question_bank(5, option_count=3)


# The server picks the sector, so a student cannot choose which question to answer. Tests patch _rng.choice.
_rng = random.SystemRandom()


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


class WheelOfFortuneDefinition(QuestionBankTemplateDefinition):
    metadata = TemplateMetadata(
        key="wheel_of_fortune",
        title="Колесо фортуны",
        description="Запуск вращения, остановка на секторе и ответ на выпавший вопрос.",
        playable=True,
    )
    editor_form_class = WheelEditorForm
    player_template_name = "player/wheel_of_fortune.html"
    preview_template_name = "player/wheel_of_fortune.html"
    editor_question_default_points = DEFAULT_QUESTION_POINTS
    answer_actions = frozenset({"answer", "answer_wheel"})
    allows_early_finish = True
    review_item_label = "Сектор"

    def default_config(self) -> dict[str, Any]:
        return {
            "scoring_enabled": True,
            "no_repeat": True,
            "reveal_correct_answer": True,
            "items": _sample_items(),
        }

    def build_editor_initial(self, config: dict[str, Any]) -> dict[str, Any]:
        items = normalize_question_bank(config, default_points=DEFAULT_QUESTION_POINTS)
        return {
            "disable_scoring": not is_scoring_enabled(config),
            "no_repeat": config.get("no_repeat", True),
            "reveal_correct_answer": config.get("reveal_correct_answer", True),
            "items_json": serialize_question_bank_editor(items, default_points=DEFAULT_QUESTION_POINTS),
            "items_text": serialize_question_bank(items, default_points=DEFAULT_QUESTION_POINTS),
        }

    def build_config(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "scoring_enabled": not cleaned_data.get("disable_scoring", False),
            "no_repeat": cleaned_data.get("no_repeat", False),
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
        scoring_enabled = is_scoring_enabled(config)
        states = self.build_item_states(activity, session, preview=preview)
        active_key = str(session.runtime_state.get("active_item", "")) if session else ""
        # The question the wheel stopped on and the student has not answered yet: a reload shows it again.
        active_item = next((state for state in states if state["id"] == active_key and not state["is_answered"]), None)
        fills = _wheel_sector_fills(len(states))
        sectors = [
            {
                **state,
                "label": state["points"] if scoring_enabled else state["number"],
                "is_active": active_item is not None and state["id"] == active_item["id"],
                "fill": fills[index],
            }
            for index, state in enumerate(states)
        ]
        answered_count = sum(1 for state in states if state["is_answered"])
        return {
            # No answer key here: options and, for answered sectors, the feedback the reveal policy allows.
            "sectors": sectors,
            "active_item": active_item,
            "active_item_id": active_item["id"] if active_item else "",
            "answered_count": answered_count,
            "total_count": len(states),
            "remaining_count": len(states) - answered_count,
            "max_score": self.get_max_score(config),
            "preview": preview,
            "no_repeat": self.no_repeat(config),
            "reveal_correct_answer": self.reveals_correct_option(config),
            "scoring_enabled": scoring_enabled,
        }

    def no_repeat(self, config: dict[str, Any]) -> bool:
        return bool(config.get("no_repeat", True))

    def answer_item_key(self, activity: Any, session: Any, payload: Any) -> str:
        active_key = str(session.runtime_state.get("active_item", ""))
        posted_key = str(payload.get("item_key", "")).strip()
        if posted_key and posted_key != active_key and session.answers.filter(item_key=posted_key).exists():
            # The same answer posted again (a double click, a retry after a lost reply): the saved answer stands.
            return posted_key
        if not active_key and posted_key and str(payload.get("action", "")) == "answer_wheel":
            # Pages loaded before the server picked sectors chose the sector themselves; keep their answer.
            return posted_key
        if not active_key:
            raise ValidationError("Сначала раскрутите колесо.")
        if posted_key and posted_key != active_key:
            raise ValidationError("Ответьте на вопрос сектора, на котором остановилось колесо.")
        return active_key

    def after_answer_state(self, session: Any, item_key: str) -> dict[str, Any] | None:
        if item_key != session.runtime_state.get("active_item"):
            # A repeated answer to an earlier sector must not close the question that is open now.
            return None
        return {**session.runtime_state, "active_item": "", "last_spin": {}}

    def pick_sector(self, config: dict[str, Any], answered_keys: set[str], active_key: str) -> dict[str, Any] | None:
        """The next sector, or None when every question is answered."""
        item_ids = [item["id"] for item in self.get_items(config)]
        if active_key in item_ids and active_key not in answered_keys:
            # A question that is on screen stays until it is answered: spinning again cannot skip it.
            return {"item_key": active_key, "repeat": False, "resumed": True}
        unanswered = [item_id for item_id in item_ids if item_id not in answered_keys]
        if not unanswered:
            return None
        chosen = _rng.choice(unanswered if self.no_repeat(config) else item_ids)
        return {"item_key": chosen, "repeat": chosen in answered_keys, "resumed": False}

    def handle_custom_action(self, activity: Any, session: Any, action: str, payload: Any) -> TemplateEvaluation | None:
        if action not in {"spin", "spin_wheel"}:
            return None
        config = activity.config_json
        answers = {answer.item_key: answer for answer in session.answers.all()}
        spin = self.pick_sector(config, set(answers), str(session.runtime_state.get("active_item", "")))
        if spin is None:
            return TemplateEvaluation(is_complete=True, response={"spin": None})
        state = dict(session.runtime_state)
        if spin["repeat"]:
            # With repeats allowed the wheel may stop on a played sector: show the saved answer, spin again.
            state["active_item"] = ""
            spin["previous"] = self.build_answer_feedback(
                config, self.get_item(config, spin["item_key"]), answers[spin["item_key"]]
            )
        else:
            state["active_item"] = spin["item_key"]
        state["last_spin"] = {"item_key": spin["item_key"], "repeat": spin["repeat"]}
        return TemplateEvaluation(runtime_state=state, response={"spin": spin})

    def evaluate_preview_action(self, activity: Any, payload: Any) -> dict[str, Any]:
        action = str(payload.get("action", "")).strip()
        if action not in {"spin", "spin_wheel"}:
            return super().evaluate_preview_action(activity, payload)
        # The preview saves nothing: the browser sends what it has answered and which sector is open.
        answered = set(payload.getlist("answered")) if hasattr(payload, "getlist") else set()
        spin = self.pick_sector(activity.config_json, answered, str(payload.get("active_item", "")))
        return {"action": action, "spin": spin}
