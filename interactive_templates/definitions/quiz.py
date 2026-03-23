from __future__ import annotations

import random
from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from interactive_templates.base import (
    BaseTemplateDefinition,
    TemplateEvaluation,
    TemplateMetadata,
)
from interactive_templates.utils import non_empty_lines, split_pipe_row


class QuizEditorForm(forms.Form):
    show_result_at_end = forms.BooleanField(required=False, initial=True)
    questions_text = forms.CharField(
        label="Questions",
        widget=forms.Textarea(attrs={"rows": 12}),
        help_text="One question per line: Prompt | Correct option | Wrong option 1 | Wrong option 2",
    )


class QuizDefinition(BaseTemplateDefinition):
    metadata = TemplateMetadata(
        key="quiz",
        title="Quiz",
        description="Single-answer quiz with end-of-run scoring.",
        playable=True,
    )
    editor_form_class = QuizEditorForm
    player_template_name = "player/quiz.html"
    preview_template_name = "player/quiz.html"

    def default_config(self) -> dict[str, Any]:
        return {
            "show_result_at_end": True,
            "questions": [
                {
                    "id": f"question-{index}",
                    "prompt": f"Sample question {index}?",
                    "correct_option": f"Correct option {index}",
                    "options": [
                        f"Correct option {index}",
                        f"Wrong option A{index}",
                        f"Wrong option B{index}",
                        f"Wrong option C{index}",
                    ],
                }
                for index in range(1, 4)
            ],
        }

    def build_editor_initial(self, config: dict[str, Any]) -> dict[str, Any]:
        rows = []
        for question in config.get("questions", []):
            wrong_options = [
                option
                for option in question.get("options", [])
                if option != question.get("correct_option")
            ]
            rows.append(
                " | ".join(
                    [question.get("prompt", ""), question.get("correct_option", ""), *wrong_options]
                )
            )
        return {
            "show_result_at_end": config.get("show_result_at_end", True),
            "questions_text": "\n".join(rows),
        }

    def build_config(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        rows = non_empty_lines(cleaned_data["questions_text"])
        if not rows:
            raise ValidationError("Quiz must contain at least one question.")

        questions: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            parts = split_pipe_row(row, index)
            if len(parts) < 3:
                raise ValidationError(
                    f"Line {index} must contain prompt, correct option and at least one wrong option."
                )
            prompt = parts[0]
            correct_option = parts[1]
            wrong_options = parts[2:]
            questions.append(
                {
                    "id": f"question-{index}",
                    "prompt": prompt,
                    "correct_option": correct_option,
                    "options": [correct_option, *wrong_options],
                }
            )

        return {
            "show_result_at_end": cleaned_data.get("show_result_at_end", False),
            "questions": questions,
        }

    def build_runtime_data(
        self,
        activity: Any,
        session: Any | None = None,
        preview: bool = False,
    ) -> dict[str, Any]:
        config = activity.config_json
        answer_map = {}
        seed_base = "preview" if preview else str(session.token) if session else "anonymous"
        if session:
            answer_map = {answer.item_key: answer for answer in session.answers.all()}

        questions = []
        for index, question in enumerate(config.get("questions", []), start=1):
            shuffled = list(question["options"])
            random.Random(f"{seed_base}-{index}").shuffle(shuffled)
            answer = answer_map.get(question["id"])
            questions.append(
                {
                    "id": question["id"],
                    "prompt": question["prompt"],
                    "options": shuffled,
                    "selected_option": answer.submitted_value.get("choice") if answer else "",
                    "correct_option": question["correct_option"],
                    "is_correct": answer.is_correct if answer else None,
                }
            )

        return {
            "questions": questions,
            "show_result_at_end": config.get("show_result_at_end", True),
            "max_score": len(questions),
        }

    def get_max_score(self, config: dict[str, Any]) -> int:
        return len(config.get("questions", []))

    def evaluate_submission(
        self,
        activity: Any,
        session: Any,
        payload: dict[str, Any],
    ) -> TemplateEvaluation:
        if payload.get("action") != "submit_quiz":
            raise ValidationError("Unknown Quiz action.")

        config = activity.config_json
        answers = []
        score = 0
        max_score = self.get_max_score(config)

        for question in config.get("questions", []):
            field_name = f"question_{question['id']}"
            choice = str(payload.get(field_name, "")).strip()
            is_correct = choice == question["correct_option"]
            if is_correct:
                score += 1
            answers.append(
                {
                    "item_key": question["id"],
                    "prompt": question["prompt"],
                    "submitted_value": {
                        "choice": choice,
                        "correct_option": question["correct_option"],
                    },
                    "is_correct": is_correct,
                    "score_awarded": 1 if is_correct else 0,
                }
            )

        return TemplateEvaluation(
            score=score,
            max_score=max_score,
            is_complete=True,
            answers=answers,
            runtime_state={},
        )
