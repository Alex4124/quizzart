from __future__ import annotations

from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.contrib.auth.models import User

from accounts.models import UserProfile


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Логин")
    password = forms.CharField(
        label="Пароль",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    error_messages = {
        "invalid_login": "Не удалось войти. Проверьте логин и пароль.",
        "inactive": "Этот аккаунт временно недоступен.",
    }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update(
            {
                "placeholder": "Введите логин",
                "autocomplete": "username",
                "autofocus": True,
                "spellcheck": "false",
            }
        )
        self.fields["password"].widget.attrs.update(
            {
                "placeholder": "Введите пароль",
                "autocomplete": "current-password",
            }
        )


class RegisterForm(UserCreationForm):
    role = forms.ChoiceField(
        label="Роль в Quizzart",
        choices=UserProfile.Role.choices,
        widget=forms.RadioSelect,
    )
    email = forms.EmailField(required=True, label="Электронная почта")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["role"].label = "Роль"
        self.fields["role"].initial = UserProfile.Role.TEACHER
        self.fields["username"].label = "Логин"
        self.fields["email"].label = "Электронная почта"
        self.fields["password1"].label = "Пароль"
        self.fields["password2"].label = "Подтверждение пароля"
        self.fields["username"].widget.attrs.update(
            {
                "placeholder": "Придумайте логин",
                "autocomplete": "username",
                "spellcheck": "false",
            }
        )
        self.fields["email"].widget.attrs.update(
            {
                "placeholder": "teacher@example.com",
                "autocomplete": "email",
                "inputmode": "email",
            }
        )
        self.fields["password1"].widget.attrs.update(
            {
                "placeholder": "Не менее 8 символов",
                "autocomplete": "new-password",
            }
        )
        self.fields["password2"].widget.attrs.update(
            {
                "placeholder": "Повторите пароль",
                "autocomplete": "new-password",
            }
        )

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            profile, _ = UserProfile.objects.get_or_create(
                user=user,
                defaults={"role": self.cleaned_data["role"]},
            )
            profile.role = self.cleaned_data["role"]
            profile.save(update_fields=["role"])
        return user


class BaseProfileForm(forms.Form):
    first_name = forms.CharField(max_length=150, required=False, label="Имя")
    last_name = forms.CharField(max_length=150, required=False, label="Фамилия")
    patronymic = forms.CharField(max_length=150, required=False, label="Отчество")
    avatar = forms.ImageField(required=False, label="Фото")

    def __init__(self, *args, user: User, profile: UserProfile, **kwargs) -> None:
        self.user = user
        self.profile = profile
        initial = kwargs.setdefault("initial", {})
        initial.setdefault("first_name", user.first_name)
        initial.setdefault("last_name", user.last_name)
        initial.setdefault("patronymic", profile.patronymic)
        super().__init__(*args, **kwargs)
        self.fields["first_name"].widget.attrs.update({"placeholder": "Введите имя"})
        self.fields["last_name"].widget.attrs.update({"placeholder": "Введите фамилию"})
        self.fields["patronymic"].widget.attrs.update({"placeholder": "Введите отчество"})
        self.fields["avatar"].widget.attrs.update({"accept": "image/*"})

    def save(self) -> tuple[User, UserProfile]:
        self.user.first_name = self.cleaned_data["first_name"].strip()
        self.user.last_name = self.cleaned_data["last_name"].strip()
        self.user.save(update_fields=["first_name", "last_name"])
        self.profile.patronymic = self.cleaned_data["patronymic"].strip()
        avatar = self.cleaned_data.get("avatar")
        if avatar:
            self.profile.avatar = avatar
        return self.user, self.profile


class TeacherProfileForm(BaseProfileForm):
    teacher_subject = forms.CharField(max_length=150, required=False, label="Преподаваемый предмет")
    teacher_status = forms.CharField(
        max_length=255,
        required=False,
        label="Статус",
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Напишите статус или короткую цитату"}),
    )

    def __init__(self, *args, user: User, profile: UserProfile, **kwargs) -> None:
        initial = kwargs.setdefault("initial", {})
        initial.setdefault("teacher_subject", profile.teacher_subject)
        initial.setdefault("teacher_status", profile.teacher_status)
        super().__init__(*args, user=user, profile=profile, **kwargs)
        self.fields["teacher_subject"].widget.attrs.update({"placeholder": "Например: математика"})

    def save(self) -> tuple[User, UserProfile]:
        user, profile = super().save()
        profile.teacher_subject = self.cleaned_data["teacher_subject"].strip()
        profile.teacher_status = self.cleaned_data["teacher_status"].strip()
        profile.save(update_fields=["patronymic", "avatar", "teacher_subject", "teacher_status", "updated_at"])
        return user, profile


class StudentProfileForm(BaseProfileForm):
    student_classroom = forms.CharField(max_length=64, required=False, label="Класс")
    student_status = forms.ChoiceField(
        required=False,
        label="Статус",
        choices=[("", "Выберите статус")] + list(UserProfile.StudentStatus.choices),
    )

    def __init__(self, *args, user: User, profile: UserProfile, **kwargs) -> None:
        initial = kwargs.setdefault("initial", {})
        initial.setdefault("student_classroom", profile.student_classroom)
        initial.setdefault("student_status", profile.student_status)
        super().__init__(*args, user=user, profile=profile, **kwargs)
        self.fields["student_classroom"].widget.attrs.update({"placeholder": "Например: 7Б"})

    def save(self) -> tuple[User, UserProfile]:
        user, profile = super().save()
        profile.student_classroom = self.cleaned_data["student_classroom"].strip()
        profile.student_status = self.cleaned_data["student_status"]
        profile.save(update_fields=["patronymic", "avatar", "student_classroom", "student_status", "updated_at"])
        return user, profile


class UsernameChangeForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("username",)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Новый логин"
        self.fields["username"].widget.attrs.update(
            {
                "placeholder": "Введите новый логин",
                "autocomplete": "username",
                "spellcheck": "false",
            }
        )


class LocalizedPasswordChangeForm(PasswordChangeForm):
    def __init__(self, user, *args, **kwargs) -> None:
        super().__init__(user, *args, **kwargs)
        self.fields["old_password"].label = "Текущий пароль"
        self.fields["new_password1"].label = "Новый пароль"
        self.fields["new_password2"].label = "Подтверждение нового пароля"
        self.fields["old_password"].widget.attrs.update({"autocomplete": "current-password"})
        self.fields["new_password1"].widget.attrs.update({"autocomplete": "new-password"})
        self.fields["new_password2"].widget.attrs.update({"autocomplete": "new-password"})
