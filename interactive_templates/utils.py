from __future__ import annotations

import json
import re
import uuid
from typing import Any

from django.core.exceptions import ValidationError

DEFAULT_QUESTION_POINTS = 10
MAX_QUESTION_POINTS = 1000
# Ids end up in HTML attributes and CSS selectors, so the alphabet stays narrow.
ITEM_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

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


def validate_question_points(points: int, label: str) -> int:
    if not 0 <= points <= MAX_QUESTION_POINTS:
        raise ValidationError(f"{label}: баллы должны быть от 0 до {MAX_QUESTION_POINTS}.")
    return points


def validate_unique_options(options: list[dict[str, Any]], label: str) -> None:
    # Answers are compared by text, so a wrong option equal to the correct one would score as correct.
    seen: set[str] = set()
    for option in options:
        key = normalize_answer(option["text"])
        if key in seen:
            raise ValidationError(f"{label}: варианты ответа не должны повторяться («{option['text']}»).")
        seen.add(key)


def new_item_id() -> str:
    return f"q-{uuid.uuid4().hex[:12]}"


def assign_item_ids(
    items: list[dict[str, Any]],
    previous_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Give every question a stable id, so saved answers keep pointing at the same question after edits.

    A valid id posted by the editor is kept; otherwise an unused id of a previous question with the same
    wording is reused (older editor scripts post no ids); otherwise a fresh random id is created.
    """
    used: set[str] = set()
    for item in items:
        raw_id = str(item.get("id") or "")
        if ITEM_ID_RE.match(raw_id) and raw_id not in used:
            item["id"] = raw_id
            used.add(raw_id)
        else:
            item["id"] = ""

    free_ids_by_prompt: dict[str, list[str]] = {}
    for previous in previous_items or []:
        previous_id = str(previous.get("id") or "")
        if ITEM_ID_RE.match(previous_id) and previous_id not in used:
            free_ids_by_prompt.setdefault(normalize_answer(previous.get("prompt", "")), []).append(previous_id)

    for item in items:
        if item["id"]:
            continue
        candidates = free_ids_by_prompt.get(normalize_answer(item.get("prompt", "")), [])
        while candidates and candidates[0] in used:
            candidates.pop(0)
        if candidates:
            item["id"] = candidates.pop(0)
            used.add(item["id"])

    for item in items:
        if not item["id"]:
            item_id = new_item_id()
            while item_id in used:
                item_id = new_item_id()
            item["id"] = item_id
            used.add(item_id)
        for option_index, option in enumerate(item.get("options", []), start=1):
            option["id"] = f"{item['id']}-option-{option_index}"
    return items


def is_scoring_enabled(config: dict[str, Any]) -> bool:
    return bool(config.get("scoring_enabled", True))


def get_question_score(
    config: dict[str, Any],
    item: dict[str, Any],
    default_points: int = DEFAULT_QUESTION_POINTS,
) -> int:
    if not is_scoring_enabled(config):
        return 1
    return int(item.get("points", default_points))


def parse_question_bank_text(
    raw_text: str,
    default_points: int = DEFAULT_QUESTION_POINTS,
    previous_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
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
        # ASCII digits only: str.isdigit() also accepts "²", which int() then rejects.
        if option_parts and re.fullmatch(r"-?[0-9]+", option_parts[-1]):
            points = validate_question_points(int(option_parts[-1]), f"Строка {index}")
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
        validate_unique_options(options, f"Строка {index}")

        items.append(
            {
                "id": "",
                "prompt": prompt,
                "options": options,
                "points": points,
            }
        )

    return assign_item_ids(items, previous_items)


def serialize_question_bank_editor(
    items: list[dict[str, Any]],
    default_points: int = DEFAULT_QUESTION_POINTS,
) -> str:
    editor_items = []
    for item in items:
        editor_items.append(
            {
                "id": item.get("id", ""),
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


def parse_question_bank_editor_json(
    raw_value: str | list[dict[str, Any]],
    default_points: int = DEFAULT_QUESTION_POINTS,
    previous_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
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
        validate_unique_options(normalized_options, f"Вопрос {row_index}")

        raw_points = raw_item.get("points", default_points)
        try:
            points = int(str(raw_points).strip() or default_points)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"У вопроса {row_index} баллы должны быть целым числом.") from exc
        validate_question_points(points, f"Вопрос {row_index}")

        items.append(
            {
                "id": str(raw_item.get("id") or ""),
                "prompt": prompt,
                "options": normalized_options,
                "points": points,
            }
        )

    if not items:
        raise ValidationError("Добавьте хотя бы один вопрос.")

    return assign_item_ids(items, previous_items)


def question_bank_items_from_payload(
    items_json: str | list[dict[str, Any]] | None,
    items_text: str,
    default_points: int = DEFAULT_QUESTION_POINTS,
    previous_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if items_json:
        return parse_question_bank_editor_json(items_json, default_points=default_points, previous_items=previous_items)
    return parse_question_bank_text(items_text, default_points=default_points, previous_items=previous_items)


def serialize_question_bank(
    items: list[dict[str, Any]],
    default_points: int = DEFAULT_QUESTION_POINTS,
) -> str:
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
    *,
    config: dict[str, Any] | None = None,
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
                "points": get_question_score(config or {}, item),
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


def normalize_question_bank(
    config: dict[str, Any],
    default_points: int = DEFAULT_QUESTION_POINTS,
) -> list[dict[str, Any]]:
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


def get_question_bank_max_score(
    config: dict[str, Any],
    default_points: int = DEFAULT_QUESTION_POINTS,
) -> int:
    items = normalize_question_bank(config, default_points=default_points)
    return sum(get_question_score(config, item, default_points) for item in items)
