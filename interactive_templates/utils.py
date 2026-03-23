from __future__ import annotations


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
