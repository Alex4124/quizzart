from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase

from activities.models import Activity, ShareLink
from attempts.models import ActivitySession


class PublicPlayTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher", password="pass12345")
        self.quiz_activity = Activity.objects.create(
            owner=self.teacher,
            title="Quiz activity",
            description="Quiz",
            template_key="quiz",
            config_json={
                "show_result_at_end": True,
                "questions": [
                    {
                        "id": "question-1",
                        "prompt": "2+2?",
                        "correct_option": "4",
                        "options": ["4", "3", "5"],
                    }
                ],
            },
            status=Activity.Status.PUBLISHED,
        )
        self.share_link = ShareLink.objects.create(activity=self.quiz_activity)

    def test_student_can_complete_quiz(self):
        start_response = self.client.post(
            f"/p/{self.share_link.slug}/",
            {"action": "start", "participant_name": "Student"},
        )
        self.assertEqual(start_response.status_code, 302)

        submit_response = self.client.post(
            f"/p/{self.share_link.slug}/",
            {
                "action": "submit_quiz",
                "question_question-1": "4",
            },
        )
        self.assertEqual(submit_response.status_code, 302)
        session = ActivitySession.objects.get(activity=self.quiz_activity)
        self.assertEqual(session.status, ActivitySession.Status.COMPLETED)
        self.assertEqual(session.score, 1)

    def test_student_can_answer_choose_a_box(self):
        activity = Activity.objects.create(
            owner=self.teacher,
            title="Box activity",
            description="Boxes",
            template_key="choose_a_box",
            config_json={
                "grid_size": 6,
                "no_repeat": True,
                "boxes": [
                    {"id": "box-1", "label": "100", "prompt": "Water formula", "answer": "H2O", "points": 100},
                    {"id": "box-2", "label": "200", "prompt": "Two plus two", "answer": "4", "points": 200},
                    {"id": "box-3", "label": "300", "prompt": "Red planet", "answer": "Mars", "points": 300},
                    {"id": "box-4", "label": "400", "prompt": "Largest ocean", "answer": "Pacific", "points": 400},
                    {"id": "box-5", "label": "500", "prompt": "Python creator", "answer": "Guido", "points": 500},
                    {"id": "box-6", "label": "600", "prompt": "Capital of France", "answer": "Paris", "points": 600},
                ],
            },
            status=Activity.Status.PUBLISHED,
        )
        link = ShareLink.objects.create(activity=activity)

        self.client.post(f"/p/{link.slug}/", {"action": "start"})
        self.client.post(
            f"/p/{link.slug}/",
            {"action": "open_box", "item_key": "box-1"},
        )
        answer_response = self.client.post(
            f"/p/{link.slug}/",
            {"action": "answer_box", "item_key": "box-1", "answer": "H2O"},
        )
        self.assertEqual(answer_response.status_code, 302)
        session = ActivitySession.objects.get(activity=activity)
        self.assertEqual(session.score, 100)
