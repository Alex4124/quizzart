from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from interactive_templates.utils import (
    DEFAULT_QUESTION_POINTS,
    build_review_items,
    choice_texts,
    correct_option,
    get_question_bank_max_score,
    get_question_score,
    normalize_question_bank,
)


@dataclass(frozen=True)
class TemplateMetadata:
    key: str
    title: str
    description: str
    playable: bool
    preview_enabled: bool = True


@dataclass
class TemplateEvaluation:
    # The session service recomputes score and max_score from saved answers; these stay for compatibility.
    score: int = 0
    max_score: int = 0
    # True means "finish now" (an explicit finish); a run also completes once every item has an answer.
    is_complete: bool = False
    answers: list[dict[str, Any]] = field(default_factory=list)
    # None leaves session.runtime_state as it is.
    runtime_state: dict[str, Any] | None = None
    feedback: str = ""
    # The item whose saved answer is sent back to the browser.
    item_key: str = ""
    # Extra JSON for the browser, e.g. {"spin": {...}} for the wheel.
    response: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AnswerCheck:
    item_key: str
    prompt: str
    choice: str
    is_correct: bool
    score_awarded: int
    # Stays on the server: it goes into the saved answer, and into the page only if the reveal policy allows.
    correct_text: str

    def to_answer_row(self) -> dict[str, Any]:
        return {
            "item_key": self.item_key,
            "prompt": self.prompt,
            "submitted_value": {"choice": self.choice, "correct_option": self.correct_text},
            "is_correct": self.is_correct,
            "score_awarded": self.score_awarded,
        }


class BaseTemplateDefinition(ABC):
    metadata: TemplateMetadata
    editor_form_class: type[forms.Form]
    player_template_name = "player/not_implemented.html"
    preview_template_name = "player/not_implemented.html"
    editor_question_default_points = 10

    def get_editor_form(
        self,
        *args: Any,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> forms.Form:
        if args:
            return self.editor_form_class(*args, **kwargs)

        if config is not None and "initial" not in kwargs:
            kwargs["initial"] = self.build_editor_initial(config)
        return self.editor_form_class(**kwargs)

    @abstractmethod
    def default_config(self) -> dict[str, Any]:
        raise NotImplementedError

    def build_editor_initial(self, config: dict[str, Any]) -> dict[str, Any]:
        return config

    @abstractmethod
    def build_config(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def validate_config(self, config: dict[str, Any]) -> None:
        if not config:
            raise ValidationError("Настройки шаблона не заполнены.")

    def build_runtime_data(
        self,
        activity: Any,
        session: Any | None = None,
        preview: bool = False,
    ) -> dict[str, Any]:
        return {
            "preview": preview,
            "config": activity.config_json,
            "session": session,
        }

    def build_results_data(self, activity: Any, session: Any) -> dict[str, Any]:
        return {}

    def get_max_score(self, config: dict[str, Any]) -> int:
        return 0

    def evaluate_submission(
        self,
        activity: Any,
        session: Any,
        payload: dict[str, Any],
    ) -> TemplateEvaluation:
        raise ValidationError("Этот шаблон пока нельзя пройти.")

    def evaluate_preview_action(self, activity: Any, payload: Any) -> dict[str, Any]:
        raise ValidationError("Этот шаблон пока нельзя пройти.")


class QuestionBankTemplateDefinition(BaseTemplateDefinition):
    """A template whose items are the shared question bank and whose answers are checked on the server.

    The browser posts one answer at a time (action=answer, item_key, answer); the definition checks it, the
    session service saves it (the first saved answer is final) and recomputes the score from saved answers.
    Correct answers never reach the page unless the reveal policy allows it.
    """

    answer_actions: frozenset[str] = frozenset({"answer"})
    # Whole-run submissions from pages loaded before answers were checked one by one:
    # action -> answer field pattern, e.g. {"submit_quiz": "question_{key}"}.
    legacy_bulk_actions: dict[str, str] = {}
    # A legacy bulk submission is rejected unless every item is answered.
    legacy_bulk_requires_all = False
    allows_early_finish = False

    def get_items(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        return normalize_question_bank(config, default_points=DEFAULT_QUESTION_POINTS)

    def get_item(self, config: dict[str, Any], item_key: str) -> dict[str, Any]:
        for item in self.get_items(config):
            if str(item["id"]) == item_key:
                return item
        raise ValidationError("Задание не найдено. Обновите страницу.")

    def get_max_score(self, config: dict[str, Any]) -> int:
        return get_question_bank_max_score(config)

    def option_texts(self, config: dict[str, Any], item: dict[str, Any]) -> list[str]:
        return choice_texts(item)

    def answers_match(self, choice: str, correct_text: str) -> bool:
        return choice == correct_text

    def resolve_choice(self, config: dict[str, Any], item: dict[str, Any], choice: str) -> str | None:
        """The option the student picked, as the page shows it, or None if it is not an option of this item."""
        # Posted answers are stripped; imported configs may keep spaces around an option.
        return next((text for text in self.option_texts(config, item) if text.strip() == choice), None)

    def check_answer(self, config: dict[str, Any], item: dict[str, Any], raw_answer: Any) -> AnswerCheck:
        choice = str(raw_answer or "").strip()
        if not choice:
            raise ValidationError("Выберите ответ.")
        choice = self.resolve_choice(config, item, choice)
        if choice is None:
            raise ValidationError("Такого варианта ответа нет. Обновите страницу.")
        correct_text = correct_option(item)["text"]
        is_correct = self.answers_match(choice, correct_text)
        return AnswerCheck(
            item_key=str(item["id"]),
            prompt=item["prompt"],
            choice=choice,
            is_correct=is_correct,
            score_awarded=get_question_score(config, item) if is_correct else 0,
            correct_text=correct_text,
        )

    def reveals_correct_option(self, config: dict[str, Any]) -> bool:
        return bool(config.get("reveal_correct_answer", True))

    def reveals_correctness(self, config: dict[str, Any]) -> bool:
        return True

    def build_answer_feedback(self, config: dict[str, Any], item: dict[str, Any] | None, answer: Any) -> dict[str, Any]:
        """What the page may learn about a saved answer. Built from a fixed list of fields on purpose."""
        if isinstance(answer, AnswerCheck):
            submitted, is_correct, score_awarded = answer.choice, answer.is_correct, answer.score_awarded
        else:
            submitted_value = answer.submitted_value or {}
            submitted = submitted_value.get("choice", submitted_value.get("answer", ""))
            is_correct, score_awarded = answer.is_correct, answer.score_awarded
        shows_correctness = self.reveals_correctness(config)
        correct_text = None
        if item is not None and shows_correctness and self.reveals_correct_option(config):
            correct_text = correct_option(item)["text"]
        return {
            "submitted": submitted,
            "is_correct": bool(is_correct) if shows_correctness else None,
            "correct_option": correct_text,
            "score_awarded": score_awarded if shows_correctness else None,
        }

    def score_answers(self, config: dict[str, Any], answers: Iterable[Any]) -> tuple[int, int]:
        """Score from saved answers against the current questions and points."""
        items = {str(item["id"]): item for item in self.get_items(config)}
        score = sum(
            get_question_score(config, items[answer.item_key])
            for answer in answers
            if answer.is_correct and answer.item_key in items
        )
        return score, sum(get_question_score(config, item) for item in items.values())

    def is_complete(self, config: dict[str, Any], answered_keys: set[str]) -> bool:
        item_ids = {str(item["id"]) for item in self.get_items(config)}
        return bool(item_ids) and item_ids <= answered_keys

    def build_item_states(
        self,
        activity: Any,
        session: Any | None = None,
        *,
        preview: bool = False,
        shuffle_options: bool = True,
    ) -> list[dict[str, Any]]:
        """Per-item data every player can render: no correct answers, only feedback for saved answers."""
        config = activity.config_json
        answers_by_key = {answer.item_key: answer for answer in session.answers.all()} if session else {}
        seed_base = "preview" if preview else str(session.token) if session else "anonymous"
        states = []
        for index, item in enumerate(self.get_items(config), start=1):
            options = list(self.option_texts(config, item))
            if shuffle_options:
                # Teachers usually type the correct answer first, so authoring order would give it away.
                random.Random(f"{seed_base}-{item['id']}").shuffle(options)
            answer = answers_by_key.get(str(item["id"]))
            states.append(
                {
                    "id": str(item["id"]),
                    "number": index,
                    "prompt": item["prompt"],
                    "options": options,
                    "points": get_question_score(config, item),
                    "is_answered": answer is not None,
                    "feedback": self.build_answer_feedback(config, item, answer) if answer else None,
                }
            )
        return states

    def build_results_data(self, activity: Any, session: Any) -> dict[str, Any]:
        config = activity.config_json
        answers_by_key = {answer.item_key: answer for answer in session.answers.all()}
        return {"review_items": build_review_items(self.get_items(config), answers_by_key, config=config)}

    def handle_custom_action(self, activity: Any, session: Any, action: str, payload: Any) -> TemplateEvaluation | None:
        return None

    def answer_item_key(self, activity: Any, session: Any, payload: Any) -> str:
        return str(payload.get("item_key", "")).strip()

    def after_answer_state(self, session: Any, item_key: str) -> dict[str, Any] | None:
        return None

    def evaluate_submission(self, activity: Any, session: Any, payload: Any) -> TemplateEvaluation:
        config = activity.config_json
        action = str(payload.get("action", "")).strip()

        if action in self.answer_actions:
            item = self.get_item(config, self.answer_item_key(activity, session, payload))
            check = self.check_answer(config, item, payload.get("answer"))
            return TemplateEvaluation(
                answers=[check.to_answer_row()],
                item_key=check.item_key,
                runtime_state=self.after_answer_state(session, check.item_key),
            )

        if action in self.legacy_bulk_actions:
            return self._evaluate_legacy_bulk(config, session, payload, self.legacy_bulk_actions[action])

        if action == "finish" and self.allows_early_finish:
            return TemplateEvaluation(is_complete=True)

        evaluation = self.handle_custom_action(activity, session, action, payload)
        if evaluation is not None:
            return evaluation
        raise ValidationError(f"Неизвестное действие для шаблона «{self.metadata.title}».")

    def _evaluate_legacy_bulk(
        self,
        config: dict[str, Any],
        session: Any,
        payload: Any,
        field_pattern: str,
    ) -> TemplateEvaluation:
        rows = []
        answered = {answer.item_key for answer in session.answers.all()}
        for item in self.get_items(config):
            raw = payload.get(field_pattern.format(key=item["id"]), "")
            if not str(raw or "").strip():
                continue
            try:
                rows.append(self.check_answer(config, item, raw).to_answer_row())
            except ValidationError:
                continue
            answered.add(str(item["id"]))
        if self.legacy_bulk_requires_all and not self.is_complete(config, answered):
            raise ValidationError("Ответьте на все задания, прежде чем завершать.")
        return TemplateEvaluation(answers=rows, is_complete=True)

    def evaluate_preview_action(self, activity: Any, payload: Any) -> dict[str, Any]:
        """The teacher's preview: the same checks, nothing saved. The browser keeps the preview state."""
        config = activity.config_json
        action = str(payload.get("action", "")).strip()
        if action not in self.answer_actions:
            raise ValidationError("В предпросмотре это действие недоступно.")
        item = self.get_item(config, str(payload.get("item_key", "")).strip())
        check = self.check_answer(config, item, payload.get("answer"))
        return {"action": action, "item_key": item["id"], "feedback": self.build_answer_feedback(config, item, check)}
