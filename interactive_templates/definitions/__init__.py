from __future__ import annotations

from interactive_templates.definitions.categorize import CategorizeDefinition
from interactive_templates.definitions.choose_a_box import ChooseABoxDefinition
from interactive_templates.definitions.matching import MatchingDefinition
from interactive_templates.definitions.quiz import QuizDefinition
from interactive_templates.definitions.wheel_of_fortune import WheelOfFortuneDefinition
from interactive_templates.registry import registry


def register_all_templates() -> None:
    definitions = [
        ChooseABoxDefinition(),
        QuizDefinition(),
        WheelOfFortuneDefinition(),
        MatchingDefinition(),
        CategorizeDefinition(),
    ]
    for definition in definitions:
        registry.register(definition)
