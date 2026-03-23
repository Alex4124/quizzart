from __future__ import annotations

from django.urls import path

from dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("", views.landing, name="landing"),
    path("dashboard/", views.home, name="home"),
    path("activities/<int:pk>/analytics/", views.activity_analytics, name="analytics"),
]
