from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from django import forms
from django.core.exceptions import ValidationError


@dataclass(frozen=True)
class TemplateMetadata:
    key: str
    title: str
    description: str
    playable: bool
    preview_enabled: bool = True


@dataclass
class TemplateEvaluation:
    score: int
    max_score: int
    is_complete: bool
    answers: list[dict[str, Any]] = field(default_factory=list)
    runtime_state: dict[str, Any] = field(default_factory=dict)
    feedback: str = ""


class BaseTemplateDefinition(ABC):
    metadata: TemplateMetadata
    editor_form_class: type[forms.Form]
    player_template_name = "player/not_implemented.html"
    preview_template_name = "player/not_implemented.html"

    def get_editor_form(
        self,
        *args: Any,
        config: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> forms.Form:
        if args:
            return self.editor_form_class(*args, **kwargs)

        if config is not None and "initial" not in kwargs:
            kwargs["initial"] = self.build_editor_initial(config)
        return self.editor_form_class(**kwargs)

    @abstractmethod
    def default_config(self) -> dict[str, Any]:
        raise NotImplementedError

    def build_editor_initial(self, config: dict[str, Any]) -> dict[str, Any]:
        return config

    @abstractmethod
    def build_config(self, cleaned_data: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def validate_config(self, config: dict[str, Any]) -> None:
        if not config:
            raise ValidationError("Template configuration cannot be empty.")

    def build_runtime_data(
        self,
        activity: Any,
        session: Any | None = None,
        preview: bool = False,
    ) -> dict[str, Any]:
        return {
            "preview": preview,
            "config": activity.config_json,
            "session": session,
        }

    def get_max_score(self, config: dict[str, Any]) -> int:
        return 0

    def evaluate_submission(
        self,
        activity: Any,
        session: Any,
        payload: dict[str, Any],
    ) -> TemplateEvaluation:
        raise ValidationError("This template is registered but not playable yet.")
