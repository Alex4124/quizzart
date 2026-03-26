from __future__ import annotations

from accounts.services import (
    ensure_user_profile,
    profile_full_name,
    profile_initials,
    profile_short_name,
    user_home_url,
)


def account_navigation(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}

    profile = ensure_user_profile(request.user)
    return {
        "current_user_profile": profile,
        "current_user_display_name": profile_full_name(request.user, profile),
        "current_user_short_name": profile_short_name(request.user, profile),
        "current_user_initials": profile_initials(request.user, profile),
        "current_user_avatar_url": profile.avatar.url if profile.avatar else "",
        "current_user_home_url": user_home_url(request.user),
    }
