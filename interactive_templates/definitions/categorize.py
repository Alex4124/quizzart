from __future__ import annotations

from typing import Any

from django import forms

from interactive_templates.base import BaseTemplateDefinition, TemplateMetadata
from interactive_templates.utils import non_empty_lines


class CategorizeEditorForm(forms.Form):
    categories_text = forms.CharField(
        label="Categories",
        widget=forms.Textarea(attrs={"rows": 4}),
        help_text="One category per line.",
    )
    items_text = forms.CharField(
        label="Items",
        widget=forms.Textarea(attrs={"rows": 8}),
        help_text="One item per line: Label | Category",
    )


class CategorizeDefinition(BaseTemplateDefinition):
    metadata = TemplateMetadata(
        key="categorize",
        title="Categorize",
        description="Registered architecture slot for categorization games.",
        playable=False,
    )
    editor_form_class = CategorizeEditorForm

    def default_config(self) -> dict[str, Any]:
        return {
            "categories": ["Nouns", "Verbs"],
            "items": [
                {"label": "Run", "category": "Verbs"},
                {"label": "Teacher", "category": "Nouns"},
            ],
        }

    def build_editor_initial(self, config: dict[str, Any]) -> dict[str, Any]:
        item_rows = [f"{item['label']} | {item['category']}" for item in config.get("items", [])]
        return {
            "categories_text": "\n".join(config.get("categories", [])),
            "items_text": "\n".join(item_rows),
        }

    def build_config(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        categories = non_empty_lines(cleaned_data["categories_text"])
        items = []
        for row in non_empty_lines(cleaned_data["items_text"]):
            parts = [part.strip() for part in row.split("|", maxsplit=1)]
            if len(parts) != 2:
                continue
            items.append({"label": parts[0], "category": parts[1]})
        return {"categories": categories, "items": items}

    def build_runtime_data(
        self,
        activity: Any,
        session: Any | None = None,
        preview: bool = False,
    ) -> dict[str, Any]:
        config = activity.config_json
        return {
            "items": config.get("items", []),
            "summary": f"{len(config.get('categories', []))} categories, {len(config.get('items', []))} items.",
            "preview": preview,
        }
