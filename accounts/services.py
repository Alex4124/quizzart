from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import UserProfile


User = get_user_model()


def ensure_user_profile(user: User) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={"role": UserProfile.Role.TEACHER},
    )
    return profile


def profile_full_name(user: User, profile: UserProfile | None = None) -> str:
    profile = profile or ensure_user_profile(user)
    parts = [
        user.last_name.strip(),
        user.first_name.strip(),
        profile.patronymic.strip(),
    ]
    full_name = " ".join(part for part in parts if part)
    return full_name or user.get_username()


def profile_short_name(user: User, profile: UserProfile | None = None) -> str:
    profile = profile or ensure_user_profile(user)
    if user.first_name.strip():
        return user.first_name.strip()
    full_name = profile_full_name(user, profile)
    return full_name.split()[0] if full_name else user.get_username()


def profile_initials(user: User, profile: UserProfile | None = None) -> str:
    profile = profile or ensure_user_profile(user)
    first_name = user.first_name.strip()
    last_name = user.last_name.strip()

    initials = ""
    if first_name:
        initials += first_name[:1].upper()
    if last_name:
        initials += last_name[:1].upper()
    if initials:
        return initials

    full_name = profile_full_name(user, profile)
    if full_name:
        parts = full_name.split()
        if len(parts) >= 2:
            return f"{parts[0][:1]}{parts[1][:1]}".upper()
        return parts[0][:1].upper()
    return user.get_username()[:1].upper()


def user_home_url(user: User) -> str:
    profile = ensure_user_profile(user)
    if profile.is_teacher:
        return reverse("dashboard:home")
    return reverse("accounts:profile")


def is_teacher(user: User) -> bool:
    return user.is_authenticated and ensure_user_profile(user).is_teacher


def is_student(user: User) -> bool:
    return user.is_authenticated and ensure_user_profile(user).is_student
