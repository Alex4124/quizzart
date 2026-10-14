from __future__ import annotations

from django import forms


class QuestionBankEditorForm(forms.Form):
    disable_scoring = forms.BooleanField(
        required=False,
        initial=False,
        label="Не считать баллы",
        help_text="Система будет учитывать только количество правильных ответов.",
    )
    items_json = forms.CharField(required=False, widget=forms.HiddenInput())
    items_text = forms.CharField(required=False, widget=forms.HiddenInput())
