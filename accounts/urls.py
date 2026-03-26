from __future__ import annotations

from django.contrib.auth.views import LogoutView
from django.urls import path

from accounts import views

app_name = "accounts"

urlpatterns = [
    path(
        "login/",
        views.RoleAwareLoginView.as_view(),
        name="login",
    ),
    path("logout/", LogoutView.as_view(next_page="dashboard:landing"), name="logout"),
    path("register/", views.register, name="register"),
    path("profile/", views.profile, name="profile"),
]
