from __future__ import annotations

import re

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from activities.models import Activity, ShareLink
from attempts.models import ActivitySession


User = get_user_model()


class LandingViewTests(TestCase):
    def test_anonymous_user_sees_marketing_landing(self):
        response = self.client.get(reverse("dashboard:landing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Сделайте обучение")
        self.assertContains(response, "Начать бесплатно")
        self.assertContains(response, "Выберите свой стиль проведения занятия.")

    def test_authenticated_user_is_redirected_to_dashboard(self):
        user = User.objects.create_user(
            username="teacher",
            password="pass12345",
            email="teacher@example.com",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("dashboard:landing"))

        self.assertRedirects(response, reverse("dashboard:home"))

    def test_authenticated_student_is_redirected_to_profile(self):
        user = User.objects.create_user(
            username="student",
            password="pass12345",
            email="student@example.com",
        )
        UserProfile.objects.create(user=user, role=UserProfile.Role.STUDENT)
        self.client.force_login(user)

        response = self.client.get(reverse("dashboard:landing"))

        self.assertRedirects(response, reverse("accounts:profile"))


class BaseLayoutSmokeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="teacher-smoke",
            password="pass12345",
            email="smoke@example.com",
        )

    def test_login_and_register_pages_render(self):
        login_response = self.client.get(reverse("accounts:login"))
        register_response = self.client.get(reverse("accounts:register"))

        self.assertEqual(login_response.status_code, 200)
        self.assertContains(login_response, "С возвращением")
        self.assertEqual(register_response.status_code, 200)
        self.assertContains(register_response, "Создайте аккаунт")

    def test_dashboard_home_renders_for_authenticated_user(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "С возвращением")
        self.assertContains(response, reverse("accounts:profile"))

    def test_logout_redirects_to_landing_page(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("accounts:logout"))

        self.assertRedirects(response, reverse("dashboard:landing"))


class DashboardHomeViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="teacher-dashboard",
            password="pass12345",
            email="dashboard@example.com",
            first_name="Sara",
        )
        self.client.force_login(self.user)

    def _question_bank(self, count: int = 3) -> dict:
        return {
            "items": [
                {
                    "id": f"item-{index}",
                    "prompt": f"Question {index}",
                    "points": 1,
                    "options": [
                        {"id": f"item-{index}-a", "text": "Correct", "is_correct": True},
                        {"id": f"item-{index}-b", "text": "Wrong", "is_correct": False},
                    ],
                }
                for index in range(1, count + 1)
            ]
        }

    def _create_activity(
        self,
        *,
        title: str,
        description: str,
        template_key: str = "quiz",
        published: bool = False,
    ) -> Activity:
        activity = Activity.objects.create(
            owner=self.user,
            title=title,
            description=description,
            template_key=template_key,
            config_json=self._question_bank(),
        )
        if published:
            activity.publish()
            activity.save(update_fields=["status", "published_at", "updated_at"])
        return activity

    def test_dashboard_home_renders_teacher_workspace_layout(self):
        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "С возвращением, Sara")
        self.assertContains(response, "Создать интерактив")
        self.assertContains(response, "Последние события")
        self.assertContains(response, reverse("accounts:profile"))
        self.assertNotContains(response, "Ресурсы")
        self.assertNotContains(response, "Настройки")

    def test_student_is_redirected_from_teacher_dashboard(self):
        student = User.objects.create_user(
            username="student-dashboard",
            password="pass12345",
            email="student-dashboard@example.com",
        )
        UserProfile.objects.create(user=student, role=UserProfile.Role.STUDENT)
        self.client.force_login(student)

        response = self.client.get(reverse("dashboard:home"))

        self.assertRedirects(response, reverse("accounts:profile"))

    def test_student_is_redirected_from_teacher_analytics(self):
        activity = self._create_activity(
            title="Алгебра",
            description="Проверка",
            published=True,
        )
        student = User.objects.create_user(
            username="student-analytics",
            password="pass12345",
            email="student-analytics@example.com",
        )
        UserProfile.objects.create(user=student, role=UserProfile.Role.STUDENT)
        self.client.force_login(student)

        response = self.client.get(reverse("dashboard:analytics", args=[activity.pk]))

        self.assertRedirects(response, reverse("accounts:profile"))

    def test_dashboard_metrics_and_feed_use_real_activity_data(self):
        activity = self._create_activity(
            title="Квантовая физика 101",
            description="Разбор базовых понятий и проверка по итогам урока.",
            published=True,
        )
        share_link = ShareLink.objects.create(activity=activity, slug="physics101")
        ActivitySession.objects.create(
            activity=activity,
            share_link=share_link,
            participant_name="Анна",
            status=ActivitySession.Status.STARTED,
        )
        completed_session = ActivitySession.objects.create(
            activity=activity,
            share_link=share_link,
            participant_name="James Miller",
        )
        completed_session.mark_completed(score=92, max_score=100)
        completed_session.save(
            update_fields=["status", "completed_at", "score", "max_score", "percent_score"]
        )

        response = self.client.get(reverse("dashboard:home"))
        markup = response.content.decode()
        meta_match = re.search(r'<div class="teacher-activity-card__meta">(.*?)</div>', markup, re.S)

        self.assertContains(response, "2 запуска всего")
        self.assertContains(response, "1 завершение в выборке")
        self.assertContains(response, "92.0%")
        self.assertIsNotNone(meta_match)
        self.assertEqual(meta_match.group(1).count("<span>"), 2)
        self.assertContains(response, "Начата сессия")
        self.assertContains(response, "Завершено прохождение")
        self.assertContains(response, "Активность опубликована")
        self.assertContains(response, "James Miller")
        self.assertContains(response, "Анна")

    def test_dashboard_search_filters_by_template_title_and_text(self):
        quiz_activity = self._create_activity(
            title="Случайный заголовок",
            description="Описание для викторины.",
            template_key="quiz",
        )
        other_activity = self._create_activity(
            title="Змейка по биологии",
            description="Повторение терминов.",
            template_key="snake",
        )

        response = self.client.get(reverse("dashboard:home"), {"q": "викторина"})

        self.assertContains(response, quiz_activity.title)
        self.assertNotContains(response, other_activity.title)
        self.assertContains(response, "Результаты поиска")

    def test_dashboard_activity_card_renders_actions_question_count_and_share_link(self):
        activity = self._create_activity(
            title="Неорганическая химия",
            description="Лабораторная работа по оксидам и основаниям.",
            published=True,
        )
        share_link = ShareLink.objects.create(activity=activity, slug="chemistry-lab")

        response = self.client.get(reverse("dashboard:home"))
        markup = response.content.decode()

        self.assertContains(response, "3 вопросов")
        self.assertContains(response, reverse("activities:edit", kwargs={"pk": activity.pk}))
        self.assertContains(response, reverse("activities:preview", kwargs={"pk": activity.pk}))
        self.assertContains(response, reverse("dashboard:analytics", kwargs={"pk": activity.pk}))
        self.assertNotIn("teacher-activity-card__cover-label", markup)
        self.assertNotContains(response, reverse("activities:duplicate", kwargs={"pk": activity.pk}))
        self.assertContains(response, f'data-copy-link="http://testserver{share_link.get_absolute_url()}"')
        self.assertContains(response, "data-copy-toast")
        self.assertContains(response, "Опубликован", count=1)

    def test_dashboard_shows_all_teacher_activities_without_truncation(self):
        first = self._create_activity(
            title="Алгебра: уравнения",
            description="Первый интерактив.",
        )
        second = self._create_activity(
            title="История: реформы",
            description="Второй интерактив.",
        )
        third = self._create_activity(
            title="Литература: символизм",
            description="Третий интерактив.",
        )
        fourth = self._create_activity(
            title="География: климат",
            description="Четвёртый интерактив.",
        )

        response = self.client.get(reverse("dashboard:home"))

        self.assertContains(response, "Все активности")
        self.assertContains(response, first.title)
        self.assertContains(response, second.title)
        self.assertContains(response, third.title)
        self.assertContains(response, fourth.title)
