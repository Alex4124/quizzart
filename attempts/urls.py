from __future__ import annotations

from django.urls import path

from attempts import views

app_name = "attempts"

urlpatterns = [
    path("<slug:slug>/", views.play, name="play"),
    path("<slug:slug>/results/", views.results, name="results"),
]
