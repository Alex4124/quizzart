from django.contrib import admin

from accounts.models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "role",
        "teacher_subject",
        "student_classroom",
        "updated_at",
    )
    list_filter = ("role", "student_status")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "patronymic",
        "teacher_subject",
        "student_classroom",
    )
