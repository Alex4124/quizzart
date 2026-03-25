from __future__ import annotations

import json
from typing import Any

from django.core.exceptions import ValidationError

QUESTION_BANK_HELP_TEXT = (
    "Одна строка на вопрос: Вопрос | *Правильный ответ | Неверный 1 | Неверный 2 | необязательные баллы"
)


def non_empty_lines(raw_text: str) -> list[str]:
    return [line.strip() for line in raw_text.splitlines() if line.strip()]


def split_pipe_row(raw_line: str, line_number: int) -> list[str]:
    parts = [part.strip() for part in raw_line.split("|")]
    if len(parts) < 2:
        raise ValueError(
            f"Line {line_number} must contain at least two pipe-separated values."
        )
    return parts


def normalize_answer(value: str) -> str:
    return " ".join(value.lower().strip().split())


def parse_question_bank_text(raw_text: str, default_points: int = 1) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    rows = non_empty_lines(raw_text)
    if not rows:
        raise ValidationError("Добавьте хотя бы одну строку с вопросом.")

    for index, row in enumerate(rows, start=1):
        parts = [part.strip() for part in row.split("|") if part.strip()]
        if len(parts) < 3:
            raise ValidationError(
                f"Строка {index} должна содержать вопрос и минимум два варианта ответа."
            )

        prompt = parts[0]
        option_parts = parts[1:]
        points = default_points
        if option_parts and option_parts[-1].lstrip("-").isdigit():
            points = int(option_parts[-1])
            option_parts = option_parts[:-1]

        if len(option_parts) < 2:
            raise ValidationError(f"В строке {index} после баллов должно остаться минимум два варианта.")

        options: list[dict[str, Any]] = []
        correct_count = 0
        for option_index, raw_option in enumerate(option_parts, start=1):
            is_correct = raw_option.startswith("*")
            option_text = raw_option[1:].strip() if is_correct else raw_option
            if not option_text:
                raise ValidationError(f"В строке {index} найден пустой вариант ответа.")
            if is_correct:
                correct_count += 1
            options.append(
                {
                    "id": f"item-{index}-option-{option_index}",
                    "text": option_text,
                    "is_correct": is_correct,
                }
            )

        if correct_count != 1:
            raise ValidationError(f"В строке {index} должен быть ровно один правильный ответ, помеченный *.")

        items.append(
            {
                "id": f"item-{index}",
                "prompt": prompt,
                "options": options,
                "points": points,
            }
        )

    return items


def serialize_question_bank_editor(items: list[dict[str, Any]], default_points: int = 1) -> str:
    editor_items = []
    for item in items:
        editor_items.append(
            {
                "prompt": item.get("prompt", ""),
                "points": item.get("points", default_points),
                "options": [
                    {
                        "text": option.get("text", ""),
                        "is_correct": bool(option.get("is_correct")),
                    }
                    for option in item.get("options", [])
                ],
            }
        )
    return json.dumps(editor_items, ensure_ascii=False)


def parse_question_bank_editor_json(raw_value: str | list[dict[str, Any]], default_points: int = 1) -> list[dict[str, Any]]:
    payload = raw_value
    if isinstance(raw_value, str):
        if not raw_value.strip():
            raise ValidationError("Добавьте хотя бы один вопрос.")
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ValidationError("Не удалось прочитать вопросы из редактора.") from exc

    if not isinstance(payload, list):
        raise ValidationError("Банк вопросов должен быть списком.")

    items: list[dict[str, Any]] = []
    for row_index, raw_item in enumerate(payload, start=1):
        if not isinstance(raw_item, dict):
            raise ValidationError(f"Вопрос {row_index} передан в неверном формате.")

        prompt = str(raw_item.get("prompt", "")).strip()
        raw_options = raw_item.get("options", [])
        if not isinstance(raw_options, list):
            raise ValidationError(f"У вопроса {row_index} варианты ответа переданы в неверном формате.")

        normalized_options: list[dict[str, Any]] = []
        correct_count = 0
        has_option_content = False
        for raw_option in raw_options:
            if isinstance(raw_option, dict):
                option_text = str(raw_option.get("text", "")).strip()
                is_correct = bool(raw_option.get("is_correct"))
            else:
                option_text = str(raw_option).strip()
                is_correct = False

            if not option_text:
                continue

            has_option_content = True
            if is_correct:
                correct_count += 1
            normalized_options.append(
                {
                    "id": f"item-{len(items) + 1}-option-{len(normalized_options) + 1}",
                    "text": option_text,
                    "is_correct": is_correct,
                }
            )

        if not prompt and not has_option_content:
            continue

        if not prompt:
            raise ValidationError(f"Заполните текст вопроса {row_index}.")

        if len(normalized_options) < 2:
            raise ValidationError(f"У вопроса {row_index} должно быть минимум два заполненных ответа.")

        if correct_count != 1:
            raise ValidationError(f"У вопроса {row_index} должен быть ровно один отмеченный правильный ответ.")

        raw_points = raw_item.get("points", default_points)
        try:
            points = int(str(raw_points).strip() or default_points)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"У вопроса {row_index} баллы должны быть целым числом.") from exc

        item_index = len(items) + 1
        items.append(
            {
                "id": f"item-{item_index}",
                "prompt": prompt,
                "options": normalized_options,
                "points": points,
            }
        )

    if not items:
        raise ValidationError("Добавьте хотя бы один вопрос.")

    return items


def question_bank_items_from_payload(
    items_json: str | list[dict[str, Any]] | None,
    items_text: str,
    default_points: int = 1,
) -> list[dict[str, Any]]:
    if items_json:
        return parse_question_bank_editor_json(items_json, default_points=default_points)
    return parse_question_bank_text(items_text, default_points=default_points)


def serialize_question_bank(items: list[dict[str, Any]], default_points: int = 1) -> str:
    rows = []
    for item in items:
        options = []
        for option in item.get("options", []):
            prefix = "*" if option.get("is_correct") else ""
            options.append(f"{prefix}{option.get('text', '')}")
        points = item.get("points", default_points)
        suffix = [str(points)] if points != default_points else []
        rows.append(" | ".join([item.get("prompt", ""), *options, *suffix]))
    return "\n".join(rows)


def correct_option(item: dict[str, Any]) -> dict[str, Any]:
    for option in item.get("options", []):
        if option.get("is_correct"):
            return option
    raise ValidationError("У вопроса не найден правильный ответ.")


def choice_texts(item: dict[str, Any]) -> list[str]:
    return [option.get("text", "") for option in item.get("options", [])]


def build_review_items(
    items: list[dict[str, Any]],
    answer_map: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    review_items = []
    answer_map = answer_map or {}
    for item in items:
        answer = answer_map.get(item["id"])
        submitted_value = answer.submitted_value if answer else {}
        review_items.append(
            {
                "prompt": item["prompt"],
                "submitted": submitted_value.get("choice", submitted_value.get("answer", "")),
                "correct": correct_option(item)["text"],
                "is_correct": answer.is_correct if answer else None,
                "points": item.get("points", 0),
            }
        )
    return review_items


def _build_options(correct_text: str, distractors: list[str]) -> list[dict[str, Any]]:
    pool = [correct_text, *[value for value in distractors if value and value != correct_text]]
    unique_pool: list[str] = []
    for value in pool:
        if value not in unique_pool:
            unique_pool.append(value)
    while len(unique_pool) < 2:
        unique_pool.append(f"Option {len(unique_pool) + 1}")
    return [
        {
            "id": f"legacy-option-{index}",
            "text": value,
            "is_correct": value == correct_text,
        }
        for index, value in enumerate(unique_pool, start=1)
    ]


def normalize_question_bank(config: dict[str, Any], default_points: int = 1) -> list[dict[str, Any]]:
    if config.get("items") and config["items"] and config["items"][0].get("options"):
        return config["items"]

    if config.get("questions"):
        items = []
        for index, question in enumerate(config["questions"], start=1):
            correct_text = question["correct_option"]
            options = [
                {
                    "id": f"item-{index}-option-{option_index}",
                    "text": option,
                    "is_correct": option == correct_text,
                }
                for option_index, option in enumerate(question.get("options", []), start=1)
            ]
            items.append(
                {
                    "id": question.get("id", f"item-{index}"),
                    "prompt": question["prompt"],
                    "options": options,
                    "points": question.get("points", default_points),
                }
            )
        return items

    if config.get("boxes"):
        all_answers = [box.get("answer", "") for box in config["boxes"]]
        items = []
        for index, box in enumerate(config["boxes"], start=1):
            distractors = [answer for answer in all_answers if answer != box.get("answer", "")]
            items.append(
                {
                    "id": box.get("id", f"item-{index}"),
                    "prompt": box.get("prompt", ""),
                    "options": _build_options(box.get("answer", ""), distractors),
                    "points": box.get("points", default_points),
                }
            )
        return items

    if config.get("pairs"):
        all_right = [pair.get("right", "") for pair in config["pairs"]]
        items = []
        for index, pair in enumerate(config["pairs"], start=1):
            distractors = [value for value in all_right if value != pair.get("right", "")]
            items.append(
                {
                    "id": f"item-{index}",
                    "prompt": pair.get("left", ""),
                    "options": _build_options(pair.get("right", ""), distractors),
                    "points": default_points,
                }
            )
        return items

    if config.get("categories") and config.get("items"):
        categories = config.get("categories", [])
        items = []
        for index, item in enumerate(config["items"], start=1):
            items.append(
                {
                    "id": f"item-{index}",
                    "prompt": item.get("label", ""),
                    "options": [
                        {
                            "id": f"item-{index}-option-{option_index}",
                            "text": category,
                            "is_correct": category == item.get("category", ""),
                        }
                        for option_index, category in enumerate(categories, start=1)
                    ],
                    "points": default_points,
                }
            )
        return items

    if config.get("sectors"):
        labels = [sector.get("label", "") for sector in config["sectors"]]
        items = []
        for index, sector in enumerate(config["sectors"], start=1):
            distractors = [label for label in labels if label != sector.get("label", "")]
            items.append(
                {
                    "id": sector.get("id", f"item-{index}"),
                    "prompt": sector.get("payload", sector.get("label", "")),
                    "options": _build_options(sector.get("label", ""), distractors),
                    "points": sector.get("points", default_points),
                }
            )
        return items

    return []
