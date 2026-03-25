from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase

from activities.models import Activity, ShareLink
from attempts.models import ActivitySession


class PublicPlayTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(username="teacher", password="pass12345")

    def _create_published_activity(self, template_key: str, config_json: dict) -> ShareLink:
        activity = Activity.objects.create(
            owner=self.teacher,
            title=f"{template_key} activity",
            description=template_key,
            template_key=template_key,
            config_json=config_json,
            status=Activity.Status.PUBLISHED,
        )
        return ShareLink.objects.create(activity=activity)

    def test_student_can_complete_quiz(self):
        link = self._create_published_activity(
            "quiz",
            {
                "show_result_at_end": True,
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "2+2?",
                        "points": 1,
                        "options": [
                            {"id": "a", "text": "4", "is_correct": True},
                            {"id": "b", "text": "3", "is_correct": False},
                        ],
                    }
                ],
            },
        )
        self.client.post(f"/p/{link.slug}/", {"action": "start", "participant_name": "Student"})
        submit_response = self.client.post(
            f"/p/{link.slug}/",
            {
                "action": "submit_quiz",
                "question_item-1": "4",
            },
        )
        self.assertEqual(submit_response.status_code, 302)
        session = ActivitySession.objects.get(activity__template_key="quiz")
        self.assertEqual(session.status, ActivitySession.Status.COMPLETED)
        self.assertEqual(session.score, 1)

    def test_quiz_results_show_submitted_answers(self):
        link = self._create_published_activity(
            "quiz",
            {
                "show_result_at_end": True,
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "2+2?",
                        "points": 1,
                        "options": [
                            {"id": "a", "text": "4", "is_correct": True},
                            {"id": "b", "text": "3", "is_correct": False},
                        ],
                    },
                    {
                        "id": "item-2",
                        "prompt": "Capital of France?",
                        "points": 2,
                        "options": [
                            {"id": "a", "text": "Paris", "is_correct": True},
                            {"id": "b", "text": "Rome", "is_correct": False},
                        ],
                    },
                ],
            },
        )

        self.client.post(f"/p/{link.slug}/", {"action": "start", "participant_name": "Student"})
        self.client.post(
            f"/p/{link.slug}/",
            {
                "action": "submit_quiz",
                "question_item-1": "4",
                "question_item-2": "Paris",
            },
        )

        response = self.client.get(f"/p/{link.slug}/results/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ваш ответ: 4")
        self.assertContains(response, "Ваш ответ: Paris")
        self.assertContains(response, "100%")

    def test_student_can_answer_choose_a_box(self):
        link = self._create_published_activity(
            "choose_a_box",
            {
                "grid_size": 6,
                "no_repeat": True,
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "Water formula",
                        "points": 100,
                        "options": [
                            {"id": "a", "text": "H2O", "is_correct": True},
                            {"id": "b", "text": "CO2", "is_correct": False},
                        ],
                    }
                ],
            },
        )

        self.client.post(f"/p/{link.slug}/", {"action": "start"})
        self.client.post(f"/p/{link.slug}/", {"action": "open_box", "item_key": "item-1"})
        answer_response = self.client.post(
            f"/p/{link.slug}/",
            {"action": "answer_box", "item_key": "item-1", "answer": "H2O"},
        )
        self.assertEqual(answer_response.status_code, 302)
        session = ActivitySession.objects.get(activity__template_key="choose_a_box")
        self.assertEqual(session.score, 100)

    def test_student_can_launch_all_registered_templates(self):
        configs = {
            "wheel_of_fortune": {
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "Largest ocean?",
                        "points": 100,
                        "options": [
                            {"id": "a", "text": "Pacific", "is_correct": True},
                            {"id": "b", "text": "Atlantic", "is_correct": False},
                        ],
                    }
                ]
            },
            "matching": {
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "Python creator",
                        "points": 1,
                        "options": [
                            {"id": "a", "text": "Guido", "is_correct": True},
                            {"id": "b", "text": "Dennis", "is_correct": False},
                        ],
                    }
                ]
            },
            "categorize": {
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "Cat",
                        "points": 1,
                        "options": [
                            {"id": "a", "text": "Animals", "is_correct": True},
                            {"id": "b", "text": "Plants", "is_correct": False},
                        ],
                    }
                ]
            },
            "snake": {
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "2+2?",
                        "points": 1,
                        "options": [
                            {"id": "a", "text": "4", "is_correct": True},
                            {"id": "b", "text": "3", "is_correct": False},
                        ],
                    }
                ]
            },
        }

        for template_key, config_json in configs.items():
            with self.subTest(template_key=template_key):
                link = self._create_published_activity(template_key, config_json)
                response = self.client.get(f"/p/{link.slug}/")
                self.assertEqual(response.status_code, 200)

    def test_student_can_complete_wheel_matching_and_categorize(self):
        wheel = self._create_published_activity(
            "wheel_of_fortune",
            {
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "Largest ocean?",
                        "points": 100,
                        "options": [
                            {"id": "a", "text": "Pacific", "is_correct": True},
                            {"id": "b", "text": "Atlantic", "is_correct": False},
                        ],
                    }
                ]
            },
        )
        self.client.post(f"/p/{wheel.slug}/", {"action": "start"})
        self.client.post(f"/p/{wheel.slug}/", {"action": "spin_wheel"})
        self.client.post(f"/p/{wheel.slug}/", {"action": "answer_wheel", "answer": "Pacific"})
        self.assertEqual(
            ActivitySession.objects.get(activity__template_key="wheel_of_fortune").status,
            ActivitySession.Status.COMPLETED,
        )

        matching = self._create_published_activity(
            "matching",
            {
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "Python creator",
                        "points": 1,
                        "options": [
                            {"id": "a", "text": "Guido", "is_correct": True},
                            {"id": "b", "text": "Dennis", "is_correct": False},
                        ],
                    }
                ]
            },
        )
        self.client.post(f"/p/{matching.slug}/", {"action": "start"})
        self.client.post(
            f"/p/{matching.slug}/",
            {"action": "submit_matching", "match_item-1": "Guido"},
        )
        self.assertEqual(
            ActivitySession.objects.get(activity__template_key="matching").status,
            ActivitySession.Status.COMPLETED,
        )

        categorize = self._create_published_activity(
            "categorize",
            {
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "Cat",
                        "points": 1,
                        "options": [
                            {"id": "a", "text": "Animals", "is_correct": True},
                            {"id": "b", "text": "Plants", "is_correct": False},
                        ],
                    }
                ]
            },
        )
        self.client.post(f"/p/{categorize.slug}/", {"action": "start"})
        self.client.post(
            f"/p/{categorize.slug}/",
            {"action": "submit_categorize", "category_item-1": "Animals"},
        )
        self.assertEqual(
            ActivitySession.objects.get(activity__template_key="categorize").status,
            ActivitySession.Status.COMPLETED,
        )

    def test_student_can_complete_snake(self):
        snake = self._create_published_activity(
            "snake",
            {
                "reveal_correct_answer": True,
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "2+2?",
                        "points": 1,
                        "options": [
                            {"id": "a", "text": "4", "is_correct": True},
                            {"id": "b", "text": "3", "is_correct": False},
                        ],
                    },
                    {
                        "id": "item-2",
                        "prompt": "Largest ocean?",
                        "points": 2,
                        "options": [
                            {"id": "a", "text": "Pacific", "is_correct": True},
                            {"id": "b", "text": "Atlantic", "is_correct": False},
                        ],
                    },
                ],
            },
        )

        self.client.post(f"/p/{snake.slug}/", {"action": "start"})
        submit_response = self.client.post(
            f"/p/{snake.slug}/",
            {
                "action": "submit_snake",
                "question_item-1": "4",
                "question_item-2": "Pacific",
            },
        )

        self.assertEqual(submit_response.status_code, 302)
        session = ActivitySession.objects.get(activity__template_key="snake")
        self.assertEqual(session.status, ActivitySession.Status.COMPLETED)
        self.assertEqual(session.score, 3)

    def test_partial_snake_submit_returns_validation_error(self):
        snake = self._create_published_activity(
            "snake",
            {
                "reveal_correct_answer": True,
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "2+2?",
                        "points": 1,
                        "options": [
                            {"id": "a", "text": "4", "is_correct": True},
                            {"id": "b", "text": "3", "is_correct": False},
                        ],
                    },
                    {
                        "id": "item-2",
                        "prompt": "Largest ocean?",
                        "points": 2,
                        "options": [
                            {"id": "a", "text": "Pacific", "is_correct": True},
                            {"id": "b", "text": "Atlantic", "is_correct": False},
                        ],
                    },
                ],
            },
        )

        self.client.post(f"/p/{snake.slug}/", {"action": "start"})
        response = self.client.post(
            f"/p/{snake.slug}/",
            {
                "action": "submit_snake",
                "question_item-1": "4",
            },
        )

        self.assertEqual(response.status_code, 200)
        session = ActivitySession.objects.get(activity__template_key="snake")
        self.assertEqual(session.status, ActivitySession.Status.STARTED)
        self.assertEqual(session.answers.count(), 0)
