from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile


User = get_user_model()


class AuthPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="teacher-login",
            password="pass12345",
            email="teacher-login@example.com",
        )

    def test_login_page_renders_new_auth_layout(self):
        response = self.client.get(reverse("accounts:login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "С возвращением")
        self.assertContains(response, 'name="username"', html=False)
        self.assertContains(response, "Войти через Google")
        self.assertContains(response, "aria-disabled=\"true\"", html=False)

    def test_login_post_redirects_to_dashboard(self):
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "teacher-login", "password": "pass12345"},
        )

        self.assertRedirects(response, reverse("dashboard:home"))

    def test_student_login_redirects_to_profile(self):
        student = User.objects.create_user(
            username="student-login",
            password="pass12345",
            email="student@example.com",
        )
        UserProfile.objects.create(user=student, role=UserProfile.Role.STUDENT)

        response = self.client.post(
            reverse("accounts:login"),
            {"username": "student-login", "password": "pass12345"},
        )

        self.assertRedirects(response, reverse("accounts:profile"))

    def test_register_page_renders_new_auth_layout(self):
        response = self.client.get(reverse("accounts:register"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Создайте аккаунт")
        self.assertContains(response, 'name="role"', html=False)
        self.assertContains(response, 'name="username"', html=False)
        self.assertContains(response, 'name="email"', html=False)
        self.assertContains(response, 'name="password1"', html=False)
        self.assertContains(response, 'name="password2"', html=False)

    def test_register_creates_student_profile_and_redirects_to_profile(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "role": UserProfile.Role.STUDENT,
                "username": "new-student",
                "email": "student-new@example.com",
                "password1": "pass12345Strong",
                "password2": "pass12345Strong",
            },
        )

        self.assertRedirects(response, reverse("accounts:profile"))
        user = User.objects.get(username="new-student")
        self.assertEqual(user.profile.role, UserProfile.Role.STUDENT)

    def test_profile_page_renders_teacher_fields(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "profile-workspace-grid")
        self.assertContains(response, reverse("dashboard:home"))
        self.assertContains(response, reverse("activities:create"))
        self.assertContains(response, "Основные данные")
        self.assertContains(response, "Преподаваемый предмет")
        self.assertContains(response, "Изменить логин")
        self.assertContains(response, "Изменить пароль")

    def test_profile_page_renders_student_fields_and_status_choices(self):
        student = User.objects.create_user(
            username="student-profile",
            password="pass12345",
            email="student-profile@example.com",
            first_name="Иван",
            last_name="Петров",
        )
        UserProfile.objects.create(user=student, role=UserProfile.Role.STUDENT)
        self.client.force_login(student)

        response = self.client.get(reverse("accounts:profile"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Класс")
        self.assertContains(response, "готов учиться!")
        self.assertContains(response, "№1 в своём классе!")

    def test_user_can_change_username_and_password_from_profile(self):
        self.client.force_login(self.user)

        username_response = self.client.post(
            reverse("accounts:profile"),
            {
                "action": "change_username",
                "username": "teacher-login-updated",
            },
        )
        self.assertRedirects(username_response, reverse("accounts:profile"))

        password_response = self.client.post(
            reverse("accounts:profile"),
            {
                "action": "change_password",
                "old_password": "pass12345",
                "new_password1": "newPass12345Strong",
                "new_password2": "newPass12345Strong",
            },
        )
        self.assertRedirects(password_response, reverse("accounts:profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.username, "teacher-login-updated")
        self.assertTrue(self.user.check_password("newPass12345Strong"))
