from __future__ import annotations

import re
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import UserProfile
from activities.models import Activity, ShareLink
from attempts.models import ActivityAnswer, ActivitySession


User = get_user_model()


class LandingViewTests(TestCase):
    def test_anonymous_user_sees_marketing_landing(self):
        response = self.client.get(reverse("dashboard:landing"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'rel="icon"', html=False)
        self.assertContains(response, "browser-favicon.png")
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

    def test_dashboard_home_includes_global_favicon(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard:home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'rel="icon"', html=False)
        self.assertContains(response, "browser-favicon.png")


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


class DashboardAnalyticsViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="teacher-analytics-view",
            password="pass12345",
            email="analytics@example.com",
            first_name="Mira",
        )
        self.client.force_login(self.user)

    def _question_bank(self) -> dict:
        return {
            "items": [
                {
                    "id": "item-1",
                    "prompt": "Question 1",
                    "points": 2,
                    "options": [
                        {"id": "item-1-a", "text": "Correct 1", "is_correct": True},
                        {"id": "item-1-b", "text": "Wrong 1", "is_correct": False},
                    ],
                },
                {
                    "id": "item-2",
                    "prompt": "Question 2",
                    "points": 2,
                    "options": [
                        {"id": "item-2-a", "text": "Correct 2", "is_correct": True},
                        {"id": "item-2-b", "text": "Wrong 2", "is_correct": False},
                    ],
                },
                {
                    "id": "item-3",
                    "prompt": "Question 3",
                    "points": 2,
                    "options": [
                        {"id": "item-3-a", "text": "Correct 3", "is_correct": True},
                        {"id": "item-3-b", "text": "Wrong 3", "is_correct": False},
                    ],
                },
            ]
        }

    def _create_activity(self) -> Activity:
        return Activity.objects.create(
            owner=self.user,
            title="Analytics activity",
            description="Checking analytics details",
            template_key="quiz",
            config_json=self._question_bank(),
        )

    def _create_completed_session(
        self,
        *,
        activity: Activity,
        participant_name: str,
        score: int,
        max_score: int,
        started_at,
        duration_minutes: int,
    ) -> ActivitySession:
        session = ActivitySession.objects.create(
            activity=activity,
            participant_name=participant_name,
        )
        completed_at = started_at + timedelta(minutes=duration_minutes)
        ActivitySession.objects.filter(pk=session.pk).update(
            status=ActivitySession.Status.COMPLETED,
            score=score,
            max_score=max_score,
            percent_score=(score / max_score) * 100 if max_score else 0,
            started_at=started_at,
            completed_at=completed_at,
        )
        session.refresh_from_db()
        return session

    def test_teacher_analytics_renders_unified_layout_and_extended_metrics(self):
        activity = self._create_activity()
        started_anchor = timezone.now() - timedelta(days=1)

        boris = self._create_completed_session(
            activity=activity,
            participant_name="Boris",
            score=100,
            max_score=100,
            started_at=started_anchor,
            duration_minutes=4,
        )
        alice = self._create_completed_session(
            activity=activity,
            participant_name="Alice",
            score=80,
            max_score=100,
            started_at=started_anchor + timedelta(hours=1),
            duration_minutes=5,
        )
        clara = self._create_completed_session(
            activity=activity,
            participant_name="Clara",
            score=60,
            max_score=100,
            started_at=started_anchor + timedelta(hours=2),
            duration_minutes=6,
        )
        ActivitySession.objects.create(
            activity=activity,
            participant_name="Guest",
            status=ActivitySession.Status.STARTED,
        )

        answers = [
            (boris, "item-1", "Question 1", True),
            (boris, "item-2", "Question 2", True),
            (boris, "item-3", "Question 3", False),
            (alice, "item-1", "Question 1", False),
            (alice, "item-2", "Question 2", True),
            (alice, "item-3", "Question 3", True),
            (clara, "item-1", "Question 1", False),
            (clara, "item-2", "Question 2", True),
            (clara, "item-3", "Question 3", True),
        ]
        for session, item_key, prompt, is_correct in answers:
            ActivityAnswer.objects.create(
                session=session,
                item_key=item_key,
                prompt=prompt,
                submitted_value={"choice": "demo"},
                is_correct=is_correct,
                score_awarded=1 if is_correct else 0,
            )

        response = self.client.get(reverse("dashboard:analytics", args=[activity.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "teacher-analytics")
        self.assertContains(response, "Аналитика шаблона")
        self.assertContains(response, "Лучшие результаты")
        self.assertContains(response, "Чаще всего ошибаются")
        self.assertContains(response, "Больше всего верных ответов")
        self.assertContains(response, "Среднее время")
        self.assertContains(response, "5 мин")
        self.assertContains(response, "80,0%")
        self.assertContains(response, "Question 1")
        self.assertContains(response, "2 ошибок")
        self.assertContains(response, "Question 2")
        self.assertContains(response, "3 верных ответов")
        self.assertContains(response, "Boris")
        self.assertContains(response, "Alice")
        self.assertContains(response, "Clara")

    def test_teacher_analytics_renders_success_chart(self):
        activity = self._create_activity()
        started_anchor = timezone.now() - timedelta(days=1)
        session = self._create_completed_session(
            activity=activity,
            participant_name="Graph Student",
            score=60,
            max_score=100,
            started_at=started_anchor,
            duration_minutes=4,
        )
        ActivityAnswer.objects.create(
            session=session,
            item_key="item-1",
            prompt="Question 1",
            submitted_value={"choice": "a"},
            is_correct=True,
            score_awarded=2,
        )
        ActivityAnswer.objects.create(
            session=session,
            item_key="item-2",
            prompt="Question 2",
            submitted_value={"choice": "b"},
            is_correct=False,
            score_awarded=0,
        )
        ActivityAnswer.objects.create(
            session=session,
            item_key="item-3",
            prompt="Question 3",
            submitted_value={"choice": "c"},
            is_correct=True,
            score_awarded=2,
        )

        response = self.client.get(reverse("dashboard:analytics", args=[activity.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "teacher-analytics-chart")
        self.assertContains(response, "teacher-analytics-chart__item", count=3)
        self.assertContains(response, "Зависимость задания от числа верных ответов")
        self.assertContains(response, "Задание 1")
        self.assertContains(response, "Задание 2")
        self.assertContains(response, "Задание 3")
        self.assertContains(response, "1 верных", count=2)
