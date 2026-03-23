from __future__ import annotations

from typing import Any

from django import forms

from interactive_templates.base import BaseTemplateDefinition, TemplateMetadata
from interactive_templates.utils import non_empty_lines


class WheelEditorForm(forms.Form):
    no_repeat = forms.BooleanField(required=False, initial=True)
    sectors_text = forms.CharField(
        label="Sectors",
        widget=forms.Textarea(attrs={"rows": 10}),
        help_text="One sector per line: Label | Points | Question or action",
    )


class WheelOfFortuneDefinition(BaseTemplateDefinition):
    metadata = TemplateMetadata(
        key="wheel_of_fortune",
        title="Wheel of Fortune",
        description="Registered architecture slot for the spinning wheel template.",
        playable=False,
    )
    editor_form_class = WheelEditorForm

    def default_config(self) -> dict[str, Any]:
        return {
            "no_repeat": True,
            "sectors": [
                {"label": "Warm-up", "points": 100, "payload": "Short question"},
                {"label": "Bonus", "points": 200, "payload": "Action"},
            ],
        }

    def build_editor_initial(self, config: dict[str, Any]) -> dict[str, Any]:
        rows = [
            " | ".join(
                [sector.get("label", ""), str(sector.get("points", 0)), sector.get("payload", "")]
            )
            for sector in config.get("sectors", [])
        ]
        return {
            "no_repeat": config.get("no_repeat", True),
            "sectors_text": "\n".join(rows),
        }

    def build_config(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        sectors = []
        for index, row in enumerate(non_empty_lines(cleaned_data["sectors_text"]), start=1):
            parts = [part.strip() for part in row.split("|", maxsplit=2)]
            if len(parts) != 3:
                continue
            sectors.append(
                {
                    "id": f"sector-{index}",
                    "label": parts[0],
                    "points": int(parts[1]),
                    "payload": parts[2],
                }
            )
        return {
            "no_repeat": cleaned_data.get("no_repeat", False),
            "sectors": sectors,
        }

    def build_runtime_data(
        self,
        activity: Any,
        session: Any | None = None,
        preview: bool = False,
    ) -> dict[str, Any]:
        config = activity.config_json
        return {
            "items": config.get("sectors", []),
            "summary": f"{len(config.get('sectors', []))} sectors configured.",
            "preview": preview,
        }
