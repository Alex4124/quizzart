from django.apps import AppConfig


class ActivitiesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "activities"

    def ready(self) -> None:
        from interactive_templates.definitions import register_all_templates

        register_all_templates()
