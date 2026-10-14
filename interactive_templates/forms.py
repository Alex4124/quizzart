from __future__ import annotations

from typing import Any

from django import forms

from interactive_templates.utils import normalize_question_bank


class QuestionBankEditorForm(forms.Form):
    disable_scoring = forms.BooleanField(
        required=False,
        initial=False,
        label="Не считать баллы",
        help_text="Система будет учитывать только количество правильных ответов.",
    )
    items_json = forms.CharField(required=False, widget=forms.HiddenInput())
    items_text = forms.CharField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args: Any, previous_config: dict[str, Any] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.previous_config = previous_config or {}

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        # The saved questions let build_config keep their ids when the editor posts none.
        cleaned_data["previous_items"] = normalize_question_bank(self.previous_config) if self.previous_config else []
        return cleaned_data
