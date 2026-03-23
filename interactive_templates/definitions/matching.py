from __future__ import annotations

from typing import Any

from django import forms

from interactive_templates.base import BaseTemplateDefinition, TemplateMetadata
from interactive_templates.utils import non_empty_lines


class MatchingEditorForm(forms.Form):
    shuffle = forms.BooleanField(required=False, initial=True)
    pairs_text = forms.CharField(
        label="Pairs",
        widget=forms.Textarea(attrs={"rows": 10}),
        help_text="One pair per line: Left side | Right side",
    )


class MatchingDefinition(BaseTemplateDefinition):
    metadata = TemplateMetadata(
        key="matching",
        title="Matching",
        description="Registered architecture slot for pair matching.",
        playable=False,
    )
    editor_form_class = MatchingEditorForm

    def default_config(self) -> dict[str, Any]:
        return {
            "shuffle": True,
            "pairs": [
                {"left": "Python", "right": "Programming language"},
                {"left": "Django", "right": "Web framework"},
            ],
        }

    def build_editor_initial(self, config: dict[str, Any]) -> dict[str, Any]:
        rows = [f"{pair['left']} | {pair['right']}" for pair in config.get("pairs", [])]
        return {
            "shuffle": config.get("shuffle", True),
            "pairs_text": "\n".join(rows),
        }

    def build_config(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        pairs = []
        for row in non_empty_lines(cleaned_data["pairs_text"]):
            parts = [part.strip() for part in row.split("|", maxsplit=1)]
            if len(parts) != 2:
                continue
            pairs.append({"left": parts[0], "right": parts[1]})
        return {"shuffle": cleaned_data.get("shuffle", False), "pairs": pairs}

    def build_runtime_data(
        self,
        activity: Any,
        session: Any | None = None,
        preview: bool = False,
    ) -> dict[str, Any]:
        config = activity.config_json
        return {
            "items": config.get("pairs", []),
            "summary": f"{len(config.get('pairs', []))} pairs configured.",
            "preview": preview,
        }
