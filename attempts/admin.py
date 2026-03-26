from __future__ import annotations

from django.contrib import admin

from attempts.models import ActivityAnswer, ActivitySession


class ActivityAnswerInline(admin.TabularInline):
    model = ActivityAnswer
    extra = 0


@admin.register(ActivitySession)
class ActivitySessionAdmin(admin.ModelAdmin):
    list_display = (
        "activity",
        "participant_name",
        "participant_user",
        "status",
        "score",
        "max_score",
        "started_at",
    )
    list_filter = ("status", "activity__template_key")
    search_fields = ("activity__title", "participant_name", "participant_user__username")
    inlines = [ActivityAnswerInline]


@admin.register(ActivityAnswer)
class ActivityAnswerAdmin(admin.ModelAdmin):
    list_display = ("session", "item_key", "is_correct", "score_awarded", "answered_at")
