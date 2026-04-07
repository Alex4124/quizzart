from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase

from accounts.models import UserProfile
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
        self.assertContains(response, "player-topbar")
        self.assertContains(response, "student-player__footer")
        self.assertContains(response, "Ваш ответ: 4")
        self.assertContains(response, "Ваш ответ: Paris")
        self.assertContains(response, "100%")

    def test_quiz_flow_renders_one_active_question_card(self):
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
        response = self.client.get(f"/p/{link.slug}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "quiz-flow")
        self.assertContains(response, "quiz-stage")
        self.assertContains(response, "data-quiz-question", count=2)
        self.assertContains(response, "question-card-current", count=1)

    def test_student_can_answer_choose_a_box(self):
        link = self._create_published_activity(
            "choose_a_box",
            {
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
        answer_response = self.client.post(
            f"/p/{link.slug}/",
            {"action": "finish", "box_item-1": "H2O"},
        )
        self.assertEqual(answer_response.status_code, 302)
        session = ActivitySession.objects.get(activity__template_key="choose_a_box")
        self.assertEqual(session.score, 100)

    def test_choose_a_box_finish_persists_all_hidden_answers(self):
        link = self._create_published_activity(
            "choose_a_box",
            {
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
                    },
                    {
                        "id": "item-2",
                        "prompt": "Sun is a",
                        "points": 100,
                        "options": [
                            {"id": "a", "text": "Star", "is_correct": True},
                            {"id": "b", "text": "Planet", "is_correct": False},
                        ],
                    },
                ],
            },
        )

        self.client.post(f"/p/{link.slug}/", {"action": "start"})
        response = self.client.post(
            f"/p/{link.slug}/",
            {
                "action": "finish",
                "box_item-1": "H2O",
                "box_item-2": "Star",
            },
        )

        self.assertEqual(response.status_code, 302)
        session = ActivitySession.objects.get(activity__template_key="choose_a_box")
        self.assertEqual(session.status, ActivitySession.Status.COMPLETED)
        self.assertEqual(session.score, 200)
        self.assertEqual(session.answers.count(), 2)

    def test_choose_a_box_ajax_steps_keep_board_in_place_until_final_answer(self):
        link = self._create_published_activity(
            "choose_a_box",
            {
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
                    },
                    {
                        "id": "item-2",
                        "prompt": "Sun is a",
                        "points": 100,
                        "options": [
                            {"id": "a", "text": "Star", "is_correct": True},
                            {"id": "b", "text": "Planet", "is_correct": False},
                        ],
                    },
                ],
            },
        )

        self.client.post(f"/p/{link.slug}/", {"action": "start"})
        open_response = self.client.post(
            f"/p/{link.slug}/",
            {"action": "open_box", "item_key": "item-1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(open_response.status_code, 200)
        self.assertEqual(open_response.json()["is_complete"], False)

        session = ActivitySession.objects.get(activity__template_key="choose_a_box")
        self.assertEqual(session.runtime_state["opened"], ["item-1"])
        self.assertEqual(session.status, ActivitySession.Status.STARTED)

        answer_response = self.client.post(
            f"/p/{link.slug}/",
            {"action": "answer_box", "item_key": "item-1", "answer": "H2O"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(answer_response.status_code, 200)
        self.assertEqual(answer_response.json()["is_complete"], False)

        session.refresh_from_db()
        self.assertEqual(session.score, 100)
        self.assertEqual(session.status, ActivitySession.Status.STARTED)
        self.assertEqual(session.answers.count(), 1)

    def test_choose_a_box_ajax_final_answer_returns_results_redirect(self):
        link = self._create_published_activity(
            "choose_a_box",
            {
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
        self.client.post(
            f"/p/{link.slug}/",
            {"action": "open_box", "item_key": "item-1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        answer_response = self.client.post(
            f"/p/{link.slug}/",
            {"action": "answer_box", "item_key": "item-1", "answer": "H2O"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        payload = answer_response.json()
        self.assertEqual(answer_response.status_code, 200)
        self.assertEqual(payload["is_complete"], True)
        self.assertTrue(payload["redirect_url"].endswith(f"/p/{link.slug}/results/"))

        session = ActivitySession.objects.get(activity__template_key="choose_a_box")
        self.assertEqual(session.status, ActivitySession.Status.COMPLETED)
        self.assertEqual(session.score, 100)

    def test_choose_a_box_live_player_renders_gift_cover_and_inline_question_card(self):
        link = self._create_published_activity(
            "choose_a_box",
            {
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
        launch_response = self.client.get(f"/p/{link.slug}/")

        self.assertEqual(launch_response.status_code, 200)
        self.assertContains(launch_response, "box-gift.png")
        self.assertContains(launch_response, "data-box-cover")
        self.assertContains(launch_response, "data-box-answer-target")
        self.assertNotContains(launch_response, "правой колонке")

        opened_response = self.client.post(
            f"/p/{link.slug}/",
            {"action": "open_box", "item_key": "item-1"},
            follow=True,
        )

        self.assertEqual(opened_response.status_code, 200)
        self.assertContains(opened_response, "data-box-question-panel")
        self.assertContains(opened_response, "Water formula")
        self.assertContains(opened_response, 'name="answer_item-1"')
        self.assertNotContains(opened_response, "правой колонке")

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
                self.assertContains(response, "player-topbar")
                self.assertContains(response, "student-player__layout")

    def test_matching_flow_renders_one_question_scene_and_global_answer_bank(self):
        link = self._create_published_activity(
            "matching",
            {
                "shuffle": False,
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "Python creator",
                        "points": 1,
                        "options": [
                            {"id": "a", "text": "Guido", "is_correct": True},
                            {"id": "b", "text": "Dennis", "is_correct": False},
                        ],
                    },
                    {
                        "id": "item-2",
                        "prompt": "Django creator",
                        "points": 1,
                        "options": [
                            {"id": "a", "text": "Adrian", "is_correct": True},
                            {"id": "b", "text": "James", "is_correct": False},
                        ],
                    },
                ],
            },
        )

        response = self.client.post(f"/p/{link.slug}/", {"action": "start"}, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "matching-flow")
        self.assertContains(response, "matching-card-current", count=1)
        self.assertContains(response, 'class="matching-dock" data-matching-dock', count=2)
        self.assertContains(response, "data-matching-choice", count=4)
        self.assertContains(response, "Guido")
        self.assertContains(response, "Adrian")
        self.assertContains(response, "Dennis")
        self.assertContains(response, "James")

    def test_matching_submit_scores_only_correct_hidden_values(self):
        link = self._create_published_activity(
            "matching",
            {
                "shuffle": False,
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "Python creator",
                        "points": 1,
                        "options": [
                            {"id": "a", "text": "Guido", "is_correct": True},
                            {"id": "b", "text": "Dennis", "is_correct": False},
                        ],
                    },
                    {
                        "id": "item-2",
                        "prompt": "Django creator",
                        "points": 1,
                        "options": [
                            {"id": "a", "text": "Adrian", "is_correct": True},
                            {"id": "b", "text": "James", "is_correct": False},
                        ],
                    },
                ],
            },
        )

        self.client.post(f"/p/{link.slug}/", {"action": "start"})
        submit_response = self.client.post(
            f"/p/{link.slug}/",
            {
                "action": "submit_matching",
                "match_item-1": "Dennis",
                "match_item-2": "Adrian",
            },
        )

        self.assertEqual(submit_response.status_code, 302)
        session = ActivitySession.objects.get(activity__template_key="matching")
        self.assertEqual(session.status, ActivitySession.Status.COMPLETED)
        self.assertEqual(session.score, 1)

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
            {"action": "submit_categorize", "question_item-1": "Animals"},
        )
        self.assertEqual(
            ActivitySession.objects.get(activity__template_key="categorize").status,
            ActivitySession.Status.COMPLETED,
        )

    def test_wheel_ajax_answer_returns_json_and_keeps_session_started_until_last_question(self):
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
                    },
                    {
                        "id": "item-2",
                        "prompt": "Fastest land animal?",
                        "points": 200,
                        "options": [
                            {"id": "a", "text": "Cheetah", "is_correct": True},
                            {"id": "b", "text": "Horse", "is_correct": False},
                        ],
                    },
                ]
            },
        )

        self.client.post(f"/p/{wheel.slug}/", {"action": "start"})
        session = ActivitySession.objects.get(activity__template_key="wheel_of_fortune")
        session.runtime_state = {"active_item": "item-1"}
        session.save(update_fields=["runtime_state"])

        response = self.client.post(
            f"/p/{wheel.slug}/",
            {"action": "answer_wheel", "answer": "Pacific"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["is_complete"])

        session.refresh_from_db()
        self.assertEqual(session.status, ActivitySession.Status.STARTED)
        self.assertEqual(session.score, 100)
        self.assertEqual(session.answers.count(), 1)

    def test_wheel_ajax_final_answer_returns_redirect_payload(self):
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
        session = ActivitySession.objects.get(activity__template_key="wheel_of_fortune")
        session.runtime_state = {"active_item": "item-1"}
        session.save(update_fields=["runtime_state"])

        response = self.client.post(
            f"/p/{wheel.slug}/",
            {"action": "answer_wheel", "answer": "Pacific"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["is_complete"])
        self.assertTrue(payload["redirect_url"].endswith(f"/p/{wheel.slug}/results/"))

        session.refresh_from_db()
        self.assertEqual(session.status, ActivitySession.Status.COMPLETED)

    def test_wheel_player_renders_hud_hooks_for_live_updates(self):
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
        response = self.client.get(f"/p/{wheel.slug}/")

        self.assertContains(response, 'data-player-summary-value="score"', html=False)
        self.assertContains(response, 'data-player-summary-value="progress"', html=False)
        self.assertContains(response, 'data-player-fact-value="answered"', html=False)
        self.assertContains(response, 'data-player-fact-value="remaining"', html=False)
        self.assertContains(response, "data-player-progress-heading", html=False)
        self.assertContains(response, "data-player-progress-ring-label", html=False)
        self.assertContains(response, "data-player-progress-bar-fill", html=False)

    def test_cards_still_accept_legacy_category_field_names(self):
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
        response = self.client.post(
            f"/p/{categorize.slug}/",
            {"action": "submit_categorize", "category_item-1": "Animals"},
        )

        self.assertEqual(response.status_code, 302)
        session = ActivitySession.objects.get(activity__template_key="categorize")
        self.assertEqual(session.status, ActivitySession.Status.COMPLETED)

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

    def test_snake_player_renders_keyboard_hint_and_mobile_controls(self):
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
        response = self.client.get(f"/p/{snake.slug}/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Используйте клавиши")
        self.assertContains(response, "data-snake-dpad", html=False)
        self.assertContains(response, 'data-snake-direction="up"', html=False)
        self.assertContains(response, 'data-snake-direction="right"', html=False)
        self.assertContains(response, 'data-snake-direction="down"', html=False)
        self.assertContains(response, 'data-snake-direction="left"', html=False)
        self.assertNotContains(response, "курсор")

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

    def test_authenticated_student_launch_attaches_account_and_prefills_name(self):
        student = User.objects.create_user(
            username="student-player",
            password="pass12345",
            first_name="Иван",
            last_name="Петров",
        )
        UserProfile.objects.create(
            user=student,
            role=UserProfile.Role.STUDENT,
            patronymic="Сергеевич",
        )
        quiz = self._create_published_activity(
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

        self.client.force_login(student)
        launch_response = self.client.get(f"/p/{quiz.slug}/")
        self.assertContains(launch_response, "Петров Иван Сергеевич")

        self.client.post(f"/p/{quiz.slug}/", {"action": "start", "participant_name": ""})
        session = ActivitySession.objects.get(activity__template_key="quiz")
        self.assertEqual(session.participant_user, student)
        self.assertEqual(session.participant_name, "Петров Иван Сергеевич")
