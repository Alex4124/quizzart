from __future__ import annotations

from django import forms

from activities.models import Activity
from interactive_templates.registry import registry


class ActivityForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = ("title", "description", "template_key")
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["template_key"].choices = registry.choices()
        self.fields["title"].widget.attrs.update({"placeholder": "Weekly revision game"})
        self.fields["description"].widget.attrs.update(
            {"placeholder": "Short note for students or colleagues."}
        )
