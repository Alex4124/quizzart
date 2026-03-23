from __future__ import annotations

from django.contrib.auth.views import LoginView, LogoutView
from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path("login/", LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("register/", views.register, name="register"),
]
