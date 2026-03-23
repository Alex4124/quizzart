from __future__ import annotations

from typing import Any

from django import forms
from django.core.exceptions import ValidationError

from interactive_templates.base import (
    BaseTemplateDefinition,
    TemplateEvaluation,
    TemplateMetadata,
)
from interactive_templates.utils import non_empty_lines, normalize_answer, split_pipe_row


class ChooseABoxEditorForm(forms.Form):
    grid_size = forms.ChoiceField(
        choices=[("6", "6 boxes"), ("9", "9 boxes"), ("12", "12 boxes"), ("16", "16 boxes")],
        initial="6",
    )
    no_repeat = forms.BooleanField(
        required=False,
        initial=True,
        label="Do not allow repeating opened boxes",
    )
    boxes_text = forms.CharField(
        label="Boxes",
        widget=forms.Textarea(attrs={"rows": 10}),
        help_text="One box per line: Label | Prompt | Correct answer | Points",
    )


class ChooseABoxDefinition(BaseTemplateDefinition):
    metadata = TemplateMetadata(
        key="choose_a_box",
        title="Choose a Box",
        description="Grid of boxes with short-answer prompts and point values.",
        playable=True,
    )
    editor_form_class = ChooseABoxEditorForm
    player_template_name = "player/choose_a_box.html"
    preview_template_name = "player/choose_a_box.html"

    def default_config(self) -> dict[str, Any]:
        return {
            "grid_size": 6,
            "no_repeat": True,
            "boxes": [
                {
                    "id": f"box-{index}",
                    "label": str(index * 100),
                    "prompt": f"Sample prompt {index}",
                    "answer": f"answer {index}",
                    "points": index * 100,
                }
                for index in range(1, 7)
            ],
        }

    def build_editor_initial(self, config: dict[str, Any]) -> dict[str, Any]:
        rows = []
        for box in config.get("boxes", []):
            rows.append(
                " | ".join(
                    [
                        box.get("label", ""),
                        box.get("prompt", ""),
                        box.get("answer", ""),
                        str(box.get("points", 0)),
                    ]
                )
            )
        return {
            "grid_size": str(config.get("grid_size", 6)),
            "no_repeat": config.get("no_repeat", True),
            "boxes_text": "\n".join(rows),
        }

    def build_config(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        grid_size = int(cleaned_data["grid_size"])
        rows = non_empty_lines(cleaned_data["boxes_text"])
        if len(rows) != grid_size:
            raise ValidationError(
                f"Choose a Box expects exactly {grid_size} rows, received {len(rows)}."
            )

        boxes: list[dict[str, Any]] = []
        for index, row in enumerate(rows, start=1):
            parts = split_pipe_row(row, index)
            if len(parts) != 4:
                raise ValidationError(
                    f"Line {index} must look like: Label | Prompt | Correct answer | Points"
                )
            try:
                points = int(parts[3])
            except ValueError as exc:
                raise ValidationError(f"Line {index} has a non-numeric points value.") from exc
            boxes.append(
                {
                    "id": f"box-{index}",
                    "label": parts[0],
                    "prompt": parts[1],
                    "answer": parts[2],
                    "points": points,
                }
            )

        return {
            "grid_size": grid_size,
            "no_repeat": cleaned_data.get("no_repeat", False),
            "boxes": boxes,
        }

    def validate_config(self, config: dict[str, Any]) -> None:
        super().validate_config(config)
        if config["grid_size"] not in {6, 9, 12, 16}:
            raise ValidationError("Grid size must be one of: 6, 9, 12, 16.")

    def build_runtime_data(
        self,
        activity: Any,
        session: Any | None = None,
        preview: bool = False,
    ) -> dict[str, Any]:
        config = activity.config_json
        answers_by_key = {}
        opened_keys = set()
        if session:
            answers_by_key = {answer.item_key: answer for answer in session.answers.all()}
            opened_keys = set(session.runtime_state.get("opened", []))

        boxes = []
        for box in config.get("boxes", []):
            answer = answers_by_key.get(box["id"])
            if answer:
                state = "answered"
            elif box["id"] in opened_keys:
                state = "opened"
            else:
                state = "preview" if preview else "unopened"
            boxes.append(
                {
                    **box,
                    "state": state,
                    "submitted_answer": answer.submitted_value.get("answer", "") if answer else "",
                    "expected_answer": box["answer"],
                    "is_correct": answer.is_correct if answer else None,
                    "score_awarded": answer.score_awarded if answer else 0,
                }
            )

        return {
            "boxes": boxes,
            "grid_size": config.get("grid_size", 6),
            "no_repeat": config.get("no_repeat", False),
            "answered_count": len(answers_by_key),
            "total_boxes": len(boxes),
            "max_score": self.get_max_score(config),
            "show_finish": not preview and (answers_by_key or opened_keys),
        }

    def get_max_score(self, config: dict[str, Any]) -> int:
        return sum(box.get("points", 0) for box in config.get("boxes", []))

    def evaluate_submission(
        self,
        activity: Any,
        session: Any,
        payload: dict[str, Any],
    ) -> TemplateEvaluation:
        config = activity.config_json
        boxes = {box["id"]: box for box in config.get("boxes", [])}
        existing_answers = {answer.item_key: answer for answer in session.answers.all()}
        opened = list(session.runtime_state.get("opened", []))
        score = sum(answer.score_awarded for answer in existing_answers.values())
        max_score = self.get_max_score(config)
        action = payload.get("action")

        if action == "open_box":
            item_key = payload.get("item_key", "")
            if item_key in boxes and item_key not in opened and item_key not in existing_answers:
                opened.append(item_key)
            return TemplateEvaluation(
                score=score,
                max_score=max_score,
                is_complete=False,
                runtime_state={"opened": opened},
            )

        if action == "answer_box":
            item_key = payload.get("item_key", "")
            student_answer = str(payload.get("answer", "")).strip()
            if item_key not in boxes:
                raise ValidationError("Unknown box submitted.")
            if item_key not in opened:
                opened.append(item_key)
            if item_key in existing_answers:
                return TemplateEvaluation(
                    score=score,
                    max_score=max_score,
                    is_complete=len(existing_answers) >= len(boxes),
                    runtime_state={"opened": opened},
                )

            box = boxes[item_key]
            is_correct = normalize_answer(student_answer) == normalize_answer(box["answer"])
            score_awarded = box["points"] if is_correct else 0
            score += score_awarded
            answered_total = len(existing_answers) + 1
            return TemplateEvaluation(
                score=score,
                max_score=max_score,
                is_complete=answered_total >= len(boxes),
                runtime_state={"opened": opened},
                answers=[
                    {
                        "item_key": item_key,
                        "prompt": box["prompt"],
                        "submitted_value": {
                            "answer": student_answer,
                            "expected_answer": box["answer"],
                        },
                        "is_correct": is_correct,
                        "score_awarded": score_awarded,
                    }
                ],
            )

        if action == "finish":
            return TemplateEvaluation(
                score=score,
                max_score=max_score,
                is_complete=True,
                runtime_state={"opened": opened},
            )

        raise ValidationError("Unknown Choose a Box action.")
