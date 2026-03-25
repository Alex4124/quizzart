from __future__ import annotations

from django.urls import path

from activities import views

app_name = "activities"

urlpatterns = [
    path("new/", views.create_activity, name="create"),
    path("<int:pk>/edit/", views.edit_activity, name="edit"),
    path("<int:pk>/delete/", views.delete_activity, name="delete"),
    path("<int:pk>/preview/", views.preview_activity, name="preview"),
    path("<int:pk>/duplicate/", views.duplicate_activity_view, name="duplicate"),
]
