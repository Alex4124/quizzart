from __future__ import annotations

from django import forms


class LaunchForm(forms.Form):
    participant_name = forms.CharField(
        max_length=120,
        required=False,
        label="Your name",
        widget=forms.TextInput(attrs={"placeholder": "Optional"}),
    )
