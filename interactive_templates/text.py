from __future__ import annotations


def plural_form(value: int, one: str, few: str, many: str) -> str:
    """Russian noun form for a count: 1 вопрос, 2 вопроса, 5 вопросов, 11 вопросов, 21 вопрос."""
    remainder_hundred = abs(value) % 100
    remainder_ten = abs(value) % 10
    if 11 <= remainder_hundred <= 14:
        return many
    if remainder_ten == 1:
        return one
    if 2 <= remainder_ten <= 4:
        return few
    return many


def count_label(value: int, one: str, few: str, many: str) -> str:
    return f"{value} {plural_form(value, one, few, many)}"
