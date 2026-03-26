from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.urls import reverse
from django.shortcuts import redirect, render

from accounts.forms import (
    LocalizedPasswordChangeForm,
    LoginForm,
    RegisterForm,
    StudentProfileForm,
    TeacherProfileForm,
    UsernameChangeForm,
)
from accounts.services import ensure_user_profile, profile_full_name, profile_initials, user_home_url
from activities.models import Activity, ShareLink


class RoleAwareLoginView(LoginView):
    authentication_form = LoginForm
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_success_url(self) -> str:
        redirect_to = self.get_redirect_url()
        if redirect_to:
            return redirect_to
        return user_home_url(self.request.user)


def register(request):
    if request.user.is_authenticated:
        return redirect(user_home_url(request.user))

    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect(user_home_url(user))

    return render(request, "accounts/register.html", {"form": form})


def _profile_completion(user, profile) -> tuple[int, int, int]:
    common_values = [
        user.username.strip(),
        user.email.strip(),
        user.first_name.strip(),
        user.last_name.strip(),
        profile.patronymic.strip(),
        bool(profile.avatar),
    ]

    if profile.is_teacher:
        role_values = [
            profile.teacher_subject.strip(),
            profile.teacher_status.strip(),
        ]
    else:
        role_values = [
            profile.student_classroom.strip(),
            profile.student_status.strip(),
        ]

    values = common_values + role_values
    filled = sum(bool(value) for value in values)
    total = len(values)
    percent = round((filled / total) * 100) if total else 0
    return percent, filled, total


def _teacher_profile_summary_cards(user, profile, completion_percent, filled_fields, total_fields):
    total_activities = Activity.objects.filter(owner=user).count()
    published_activities = Activity.objects.filter(owner=user, status=Activity.Status.PUBLISHED).count()
    active_share_links = ShareLink.objects.filter(activity__owner=user, is_active=True).count()

    subject_note = profile.teacher_subject.strip() or "Предмет пока не указан"
    return [
        {
            "tone": "violet",
            "label": "Роль в Quizzart",
            "value": profile.get_role_display(),
            "note": subject_note,
            "icon": "stack",
        },
        {
            "tone": "indigo",
            "label": "Активности",
            "value": total_activities,
            "note": f"{published_activities} опубликовано, {active_share_links} ссылок активно",
            "icon": "pulse",
        },
        {
            "tone": "apricot",
            "label": "Профиль заполнен",
            "value": f"{completion_percent}%",
            "note": f"{filled_fields} из {total_fields} полей заполнено",
            "icon": "spark",
            "progress": completion_percent,
        },
    ]


def _student_profile_summary_cards(profile, completion_percent, filled_fields, total_fields):
    classroom = profile.student_classroom.strip() or "Класс не указан"
    status_note = profile.get_student_status_display() if profile.student_status else "Статус пока не выбран"
    return [
        {
            "tone": "violet",
            "label": "Роль в Quizzart",
            "value": profile.get_role_display(),
            "note": classroom,
            "icon": "stack",
        },
        {
            "tone": "indigo",
            "label": "Текущий статус",
            "value": status_note,
            "note": "Вы можете изменить его в форме профиля справа.",
            "icon": "pulse",
        },
        {
            "tone": "apricot",
            "label": "Профиль заполнен",
            "value": f"{completion_percent}%",
            "note": f"{filled_fields} из {total_fields} полей заполнено",
            "icon": "spark",
            "progress": completion_percent,
        },
    ]


@login_required
def profile(request):
    user_profile = ensure_user_profile(request.user)
    profile_form_class = TeacherProfileForm if user_profile.is_teacher else StudentProfileForm
    profile_form = profile_form_class(user=request.user, profile=user_profile)
    username_form = UsernameChangeForm(instance=request.user)
    password_form = LocalizedPasswordChangeForm(request.user)

    if request.method == "POST":
        action = request.POST.get("action", "update_profile")
        if action == "update_profile":
            profile_form = profile_form_class(
                request.POST,
                request.FILES,
                user=request.user,
                profile=user_profile,
            )
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Профиль обновлён.")
                return redirect("accounts:profile")
        elif action == "change_username":
            username_form = UsernameChangeForm(request.POST, instance=request.user)
            if username_form.is_valid():
                username_form.save()
                messages.success(request, "Логин обновлён.")
                return redirect("accounts:profile")
        elif action == "change_password":
            password_form = LocalizedPasswordChangeForm(request.user, request.POST)
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Пароль обновлён.")
                return redirect("accounts:profile")

    role_title = "учителя" if user_profile.is_teacher else "ученика"
    primary_meta = (
        user_profile.teacher_subject.strip()
        if user_profile.is_teacher
        else user_profile.student_classroom.strip()
    )
    status_text = (
        user_profile.teacher_status.strip()
        if user_profile.is_teacher
        else user_profile.get_student_status_display()
    )
    completion_percent, filled_fields, total_fields = _profile_completion(request.user, user_profile)
    summary_cards = (
        _teacher_profile_summary_cards(
            request.user,
            user_profile,
            completion_percent,
            filled_fields,
            total_fields,
        )
        if user_profile.is_teacher
        else _student_profile_summary_cards(
            user_profile,
            completion_percent,
            filled_fields,
            total_fields,
        )
    )
    short_name = request.user.first_name.strip() or profile_full_name(request.user, user_profile).split()[0]
    return render(
        request,
        "accounts/profile.html",
        {
            "profile": user_profile,
            "profile_form": profile_form,
            "username_form": username_form,
            "password_form": password_form,
            "profile_initials": profile_initials(request.user, user_profile),
            "profile_full_name": profile_full_name(request.user, user_profile),
            "role_title": role_title,
            "primary_meta": primary_meta,
            "status_text": status_text,
            "teacher_display_name": short_name,
            "teacher_initial": profile_initials(request.user, user_profile),
            "teacher_avatar_url": user_profile.avatar.url if user_profile.avatar else "",
            "dashboard_url": reverse("dashboard:home") if user_profile.is_teacher else "",
            "create_activity_url": reverse("activities:create") if user_profile.is_teacher else "",
            "summary_cards": summary_cards,
            "profile_completion": completion_percent,
            "profile_completion_text": f"{filled_fields} из {total_fields} полей заполнено",
        },
    )
