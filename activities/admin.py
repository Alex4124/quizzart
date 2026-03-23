from __future__ import annotations

from django.contrib import admin

from activities.models import Activity, ShareLink


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "template_key", "status", "updated_at")
    list_filter = ("status", "template_key")
    search_fields = ("title", "description", "owner__username")


@admin.register(ShareLink)
class ShareLinkAdmin(admin.ModelAdmin):
    list_display = ("activity", "slug", "is_active", "created_at")
    list_filter = ("is_active",)
