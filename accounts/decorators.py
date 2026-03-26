from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from accounts.services import ensure_user_profile


def teacher_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        profile = ensure_user_profile(request.user)
        if not profile.is_teacher:
            messages.info(request, "Раздел панели учителя доступен только учителям.")
            return redirect("accounts:profile")
        request.user_profile = profile
        return view_func(request, *args, **kwargs)

    return _wrapped
