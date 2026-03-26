from __future__ import annotations

import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserProfile
from activities.models import Activity
from activities.services import ensure_share_link
from interactive_templates.registry import registry


class TemplateRegistryTests(TestCase):
    def test_registry_contains_expected_templates(self):
        self.assertEqual(
            set(registry.keys()),
            {
                "choose_a_box",
                "quiz",
                "wheel_of_fortune",
                "matching",
                "categorize",
                "snake",
            },
        )


class ActivityEditorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teacher", password="pass12345")
        self.client.login(username="teacher", password="pass12345")

    def test_teacher_can_create_choose_a_box_draft(self):
        response = self.client.post(
            "/activities/new/",
            {
                "title": "Boxes",
                "description": "Practice",
                "template_key": "choose_a_box",
                "grid_size": "6",
                "no_repeat": "on",
                "items_text": "\n".join(
                    [
                        "Capital of France? | *Paris | London | Berlin | 100",
                        "Water formula? | *H2O | CO2 | O2 | 200",
                    ]
                ),
                "action": "save_draft",
            },
        )
        self.assertEqual(response.status_code, 302)
        activity = Activity.objects.get(title="Boxes")
        self.assertEqual(activity.status, Activity.Status.DRAFT)
        self.assertEqual(activity.template_key, "choose_a_box")
        self.assertEqual(len(activity.config_json["items"]), 2)

    def test_student_is_redirected_from_teacher_editor(self):
        student = User.objects.create_user(username="student-editor", password="pass12345")
        UserProfile.objects.create(user=student, role=UserProfile.Role.STUDENT)
        self.client.force_login(student)

        response = self.client.get(reverse("activities:create"))

        self.assertRedirects(response, reverse("accounts:profile"))

    def test_new_editor_renders_workspace_shell_with_tabs_and_disabled_preview(self):
        response = self.client.get(reverse("activities:create"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Общие настройки")
        self.assertContains(response, "Контент / Вопросы")
        self.assertContains(response, "Параметры шаблона")
        self.assertContains(response, "Публикация")
        self.assertContains(response, "Сначала сохраните интерактив")
        self.assertContains(response, "data-template-card", html=False)

    def test_teacher_can_publish_every_template(self):
        payloads = {
            "choose_a_box": {
                "grid_size": "6",
                "no_repeat": "on",
                "items_text": "Capital of France? | *Paris | London | Berlin | 100",
            },
            "quiz": {
                "show_result_at_end": "on",
                "items_text": "2+2? | *4 | 3 | 5",
            },
            "wheel_of_fortune": {
                "no_repeat": "on",
                "items_text": "Largest ocean? | *Pacific | Atlantic | Indian | 100",
            },
            "matching": {
                "shuffle": "on",
                "items_text": "Python creator | *Guido | Dennis | Bjarne",
            },
            "categorize": {
                "shuffle": "on",
                "items_text": "\n".join(
                    [
                        "Cat | *Animals | Plants | Minerals",
                        "Oak | *Plants | Animals | Minerals",
                    ]
                ),
            },
            "snake": {
                "reveal_correct_answer": "on",
                "items_text": "\n".join(
                    [
                        "2+2? | *4 | 3 | 5",
                        "Largest ocean? | *Pacific | Atlantic | Indian",
                    ]
                ),
            },
        }

        for template_key, extra in payloads.items():
            with self.subTest(template_key=template_key):
                response = self.client.post(
                    "/activities/new/",
                    {
                        "title": f"Activity {template_key}",
                        "description": "Publish smoke test",
                        "template_key": template_key,
                        "action": "publish",
                        **extra,
                    },
                )
                self.assertEqual(response.status_code, 302)
                activity = Activity.objects.get(title=f"Activity {template_key}")
                self.assertEqual(activity.status, Activity.Status.PUBLISHED)
                self.assertIsNotNone(activity.active_share_link)

    def test_saved_editor_renders_preview_publish_block_and_quick_actions(self):
        activity = Activity.objects.create(
            owner=self.user,
            title="Preview shell",
            description="Saved editor shell",
            template_key="quiz",
            config_json=registry.get("quiz").default_config(),
        )

        response = self.client.get(reverse("activities:edit", args=[activity.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Открыть полную симуляцию")
        self.assertContains(response, reverse("dashboard:analytics", args=[activity.pk]))
        self.assertContains(response, reverse("activities:duplicate", args=[activity.pk]))
        self.assertContains(response, reverse("activities:delete", args=[activity.pk]))

    def test_teacher_can_save_question_bank_from_structured_editor_payload(self):
        response = self.client.post(
            "/activities/new/",
            {
                "title": "Structured quiz",
                "description": "Card editor payload",
                "template_key": "quiz",
                "show_result_at_end": "on",
                "reveal_correct_answer": "on",
                "items_json": json.dumps(
                    [
                        {
                            "prompt": "Capital of France?",
                            "points": 5,
                            "options": [
                                {"text": "Paris", "is_correct": True},
                                {"text": "Berlin", "is_correct": False},
                                {"text": "Rome", "is_correct": False},
                            ],
                        }
                    ],
                    ensure_ascii=False,
                ),
                "items_text": "",
                "action": "save_draft",
            },
        )

        self.assertEqual(response.status_code, 302)
        activity = Activity.objects.get(title="Structured quiz")
        self.assertEqual(activity.template_key, "quiz")
        self.assertEqual(activity.config_json["items"][0]["prompt"], "Capital of France?")
        self.assertEqual(activity.config_json["items"][0]["points"], 5)
        self.assertEqual(activity.config_json["items"][0]["options"][0]["text"], "Paris")
        self.assertTrue(activity.config_json["items"][0]["options"][0]["is_correct"])

    def test_switching_template_preserves_posted_question_bank(self):
        response = self.client.post(
            "/activities/new/",
            {
                "title": "Switch me",
                "description": "Keep questions",
                "template_key": "quiz",
                "items_json": json.dumps(
                    [
                        {
                            "prompt": "Largest ocean?",
                            "points": 100,
                            "options": [
                                {"text": "Pacific", "is_correct": True},
                                {"text": "Atlantic", "is_correct": False},
                            ],
                        }
                    ],
                    ensure_ascii=False,
                ),
                "items_text": "",
                "action": "switch_template",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'option value="quiz" selected')
        self.assertContains(response, "Largest ocean?")
        self.assertContains(response, "Pacific")

    def test_save_changes_keeps_published_activity_published(self):
        activity = Activity.objects.create(
            owner=self.user,
            title="Published quiz",
            description="Original",
            template_key="quiz",
            config_json=registry.get("quiz").default_config(),
        )
        activity.publish()
        activity.save(update_fields=["status", "published_at", "updated_at"])
        ensure_share_link(activity)

        response = self.client.post(
            reverse("activities:edit", args=[activity.pk]),
            {
                "title": "Published quiz updated",
                "description": "Updated description",
                "template_key": "quiz",
                "show_result_at_end": "on",
                "reveal_correct_answer": "on",
                "items_json": json.dumps(
                    [
                        {
                            "prompt": "Updated question?",
                            "points": 5,
                            "options": [
                                {"text": "Correct", "is_correct": True},
                                {"text": "Wrong", "is_correct": False},
                            ],
                        }
                    ],
                    ensure_ascii=False,
                ),
                "items_text": "",
                "active_tab": "general",
                "action": "save_changes",
            },
        )

        self.assertRedirects(response, reverse("activities:edit", args=[activity.pk]))
        activity.refresh_from_db()
        self.assertEqual(activity.status, Activity.Status.PUBLISHED)
        self.assertEqual(activity.title, "Published quiz updated")
        self.assertIsNotNone(activity.active_share_link)

    def test_save_draft_unpublishes_existing_activity(self):
        activity = Activity.objects.create(
            owner=self.user,
            title="Publish me",
            description="Original",
            template_key="quiz",
            config_json=registry.get("quiz").default_config(),
        )
        activity.publish()
        activity.save(update_fields=["status", "published_at", "updated_at"])
        ensure_share_link(activity)

        response = self.client.post(
            reverse("activities:edit", args=[activity.pk]),
            {
                "title": "Publish me",
                "description": "Now draft",
                "template_key": "quiz",
                "show_result_at_end": "on",
                "reveal_correct_answer": "on",
                "items_json": json.dumps(
                    [
                        {
                            "prompt": "Question?",
                            "points": 1,
                            "options": [
                                {"text": "Correct", "is_correct": True},
                                {"text": "Wrong", "is_correct": False},
                            ],
                        }
                    ],
                    ensure_ascii=False,
                ),
                "items_text": "",
                "active_tab": "publish",
                "action": "save_draft",
            },
        )

        self.assertRedirects(response, reverse("activities:edit", args=[activity.pk]))
        activity.refresh_from_db()
        self.assertEqual(activity.status, Activity.Status.DRAFT)

    def test_switching_template_on_saved_activity_preserves_questions(self):
        activity = Activity.objects.create(
            owner=self.user,
            title="Wheel draft",
            description="Switch editor",
            template_key="wheel_of_fortune",
            config_json={
                "no_repeat": True,
                "reveal_correct_answer": True,
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "Fastest land animal?",
                        "points": 200,
                        "options": [
                            {"id": "a", "text": "Cheetah", "is_correct": True},
                            {"id": "b", "text": "Horse", "is_correct": False},
                        ],
                    }
                ],
            },
        )

        response = self.client.get(f"/activities/{activity.pk}/edit/?template_key=quiz")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'option value="quiz" selected')
        self.assertContains(response, "Fastest land animal?")
        self.assertContains(response, "Cheetah")

    def test_preview_response_allows_same_origin_iframe(self):
        activity = Activity.objects.create(
            owner=self.user,
            title="Preview quiz",
            description="Preview",
            template_key="quiz",
            config_json=registry.get("quiz").default_config(),
        )

        response = self.client.get(reverse("activities:preview", args=[activity.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertContains(response, "player-topbar")
        self.assertContains(response, "player-page--preview")

    def test_teacher_can_delete_activity_from_edit_mode(self):
        activity = Activity.objects.create(
            owner=self.user,
            title="Delete me",
            description="To remove",
            template_key="quiz",
            config_json=registry.get("quiz").default_config(),
        )

        response = self.client.post(reverse("activities:delete", args=[activity.pk]))

        self.assertRedirects(response, reverse("dashboard:home"))
        self.assertFalse(Activity.objects.filter(pk=activity.pk).exists())

    def test_choose_a_box_runtime_keeps_numbering_and_reveal_toggle(self):
        activity = Activity(
            title="Boxes preview",
            template_key="choose_a_box",
            config_json={
                "grid_size": 6,
                "no_repeat": True,
                "reveal_correct_answer": False,
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "Capital of France?",
                        "points": 100,
                        "options": [
                            {"id": "a", "text": "Paris", "is_correct": True},
                            {"id": "b", "text": "Berlin", "is_correct": False},
                        ],
                    }
                ],
            },
        )

        runtime = registry.get("choose_a_box").build_runtime_data(activity, preview=True)

        self.assertFalse(runtime["reveal_correct_answer"])
        self.assertEqual(runtime["boxes"][0]["number"], 1)
        self.assertEqual(runtime["boxes"][1]["number"], 2)

    def test_wheel_preview_renders_circle_controls_and_questions(self):
        activity = Activity.objects.create(
            owner=self.user,
            title="Wheel preview",
            description="Preview the wheel",
            template_key="wheel_of_fortune",
            config_json={
                "no_repeat": True,
                "reveal_correct_answer": True,
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
                ],
            },
        )

        response = self.client.get(reverse("activities:preview", args=[activity.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-wheel-start")
        self.assertContains(response, "data-wheel-stop")
        self.assertContains(response, "Largest ocean?")

    def test_matching_runtime_uses_global_correct_answer_bank(self):
        matching_activity = Activity(
            title="Matching preview",
            template_key="matching",
            config_json={
                "shuffle": True,
                "reveal_correct_answer": False,
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
                ],
            },
        )
        matching_runtime = registry.get("matching").build_runtime_data(matching_activity, preview=True)

        self.assertCountEqual(
            [choice["id"] for choice in matching_runtime["answer_bank"]],
            ["a", "b"],
        )
        self.assertCountEqual(
            [choice["text"] for choice in matching_runtime["answer_bank"]],
            ["Guido", "Dennis"],
        )
        self.assertCountEqual(matching_runtime["choices"], ["Guido", "Dennis"])
        self.assertTrue(matching_runtime["reveal_correct_answer"])
        self.assertEqual(matching_runtime["rows"][0]["correct_choice_id"], "a")

    def test_matching_and_categorize_preview_render_animation_hooks(self):
        matching = Activity.objects.create(
            owner=self.user,
            title="Matching preview",
            description="Matching animation",
            template_key="matching",
            config_json={
                "shuffle": True,
                "reveal_correct_answer": True,
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
                ],
            },
        )
        categorize = Activity.objects.create(
            owner=self.user,
            title="Categorize preview",
            description="Categorize animation",
            template_key="categorize",
            config_json={
                "shuffle": True,
                "reveal_correct_answer": True,
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
                ],
            },
        )

        matching_response = self.client.get(reverse("activities:preview", args=[matching.pk]))
        categorize_response = self.client.get(reverse("activities:preview", args=[categorize.pk]))

        self.assertContains(matching_response, "matching-flow")
        self.assertContains(matching_response, "data-matching-choice")
        self.assertContains(matching_response, "data-matching-question")
        self.assertContains(matching_response, "data-matching-bank")
        self.assertContains(matching_response, "data-matching-dock")
        self.assertContains(categorize_response, "data-categorize-choice")
        self.assertContains(categorize_response, "data-categorize-dock")
        self.assertContains(categorize_response, "categorize-question-cell")

    def test_snake_runtime_is_deterministic_and_preview_renders_hooks(self):
        activity = Activity.objects.create(
            owner=self.user,
            title="Snake preview",
            description="Snake animation",
            template_key="snake",
            config_json={
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

        definition = registry.get("snake")
        first_runtime = definition.build_runtime_data(activity, preview=True)
        second_runtime = definition.build_runtime_data(activity, preview=True)

        self.assertEqual(
            [(apple["id"], apple["x_percent"], apple["y_percent"]) for apple in first_runtime["apples"]],
            [(apple["id"], apple["x_percent"], apple["y_percent"]) for apple in second_runtime["apples"]],
        )

        response = self.client.get(reverse("activities:preview", args=[activity.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-snake-player")
        self.assertContains(response, "data-snake-board")
        self.assertContains(response, "data-snake-apple")
