from __future__ import annotations

from collections.abc import Iterable

from interactive_templates.base import BaseTemplateDefinition


class TemplateRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, BaseTemplateDefinition] = {}

    def register(self, definition: BaseTemplateDefinition) -> None:
        self._definitions[definition.metadata.key] = definition

    def get(self, key: str) -> BaseTemplateDefinition:
        return self._definitions[key]

    def all(self) -> list[BaseTemplateDefinition]:
        return list(self._definitions.values())

    def keys(self) -> Iterable[str]:
        return self._definitions.keys()

    def choices(self) -> list[tuple[str, str]]:
        choices: list[tuple[str, str]] = []
        for definition in self.all():
            suffix = "" if definition.metadata.playable else " (registered, runtime pending)"
            choices.append((definition.metadata.key, f"{definition.metadata.title}{suffix}"))
        return choices

    def default_key(self) -> str:
        return next(iter(self._definitions))


registry = TemplateRegistry()
