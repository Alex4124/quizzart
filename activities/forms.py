from __future__ import annotations

from django import forms

from activities.models import Activity
from interactive_templates.registry import registry


class ActivityForm(forms.ModelForm):
    template_key = forms.ChoiceField(widget=forms.HiddenInput())

    class Meta:
        model = Activity
        fields = ("title", "description", "template_key")
        labels = {
            "title": "Название",
            "description": "Описание",
            "template_key": "Шаблон",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["template_key"].choices = registry.choices()
        self.fields["title"].widget.attrs.update({"placeholder": "Повторение по теме"})
        self.fields["description"].widget.attrs.update(
            {"placeholder": "Короткое описание для учеников."}
        )
