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

    def test_all_templates_default_to_scoring_with_ten_points_per_question(self):
        for definition in registry.all():
            with self.subTest(template_key=definition.metadata.key):
                config = definition.default_config()
                editor_initial = definition.build_editor_initial(config)

                self.assertTrue(config["scoring_enabled"])
                self.assertFalse(editor_initial["disable_scoring"])
                self.assertEqual(definition.editor_question_default_points, 10)
                self.assertTrue(config["items"])
                self.assertTrue(all(item["points"] == 10 for item in config["items"]))


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
        self.assertContains(response, "Не считать баллы")
        self.assertContains(response, 'data-default-points="10"', html=False)
        self.assertContains(response, "Сначала сохраните интерактив")
        self.assertContains(response, "data-template-card", html=False)

    def test_teacher_can_publish_every_template(self):
        payloads = {
            "choose_a_box": {
                "no_repeat": "on",
                "items_text": "Capital of France? | *Paris | London | Berlin",
            },
            "quiz": {
                "show_result_at_end": "on",
                "items_text": "2+2? | *4 | 3 | Five",
            },
            "wheel_of_fortune": {
                "no_repeat": "on",
                "items_text": "Largest ocean? | *Pacific | Atlantic | Indian",
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
                        "2+2? | *4 | 3 | Five",
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
                self.assertTrue(activity.config_json["scoring_enabled"])
                self.assertEqual(activity.config_json["items"][0]["points"], 10)

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

    def test_teacher_can_disable_scoring_without_losing_custom_points(self):
        items_json = json.dumps(
            [
                {
                    "prompt": "Capital of France?",
                    "points": 37,
                    "options": [
                        {"text": "Paris", "is_correct": True},
                        {"text": "Berlin", "is_correct": False},
                    ],
                }
            ],
            ensure_ascii=False,
        )
        response = self.client.post(
            reverse("activities:create"),
            {
                "title": "Scoreless quiz",
                "description": "Count correct answers",
                "template_key": "quiz",
                "disable_scoring": "on",
                "items_json": items_json,
                "items_text": "",
                "action": "save_draft",
            },
        )

        self.assertEqual(response.status_code, 302)
        activity = Activity.objects.get(title="Scoreless quiz")
        self.assertFalse(activity.config_json["scoring_enabled"])
        self.assertEqual(activity.config_json["items"][0]["points"], 37)

        response = self.client.post(
            reverse("activities:edit", args=[activity.pk]),
            {
                "title": activity.title,
                "description": activity.description,
                "template_key": "quiz",
                "items_json": items_json,
                "items_text": "",
                "action": "save_changes",
            },
        )

        self.assertEqual(response.status_code, 302)
        activity.refresh_from_db()
        self.assertTrue(activity.config_json["scoring_enabled"])
        self.assertEqual(activity.config_json["items"][0]["points"], 37)

    def test_teacher_can_publish_matching_with_duplicate_correct_answers(self):
        response = self.client.post(
            reverse("activities:create"),
            {
                "title": "True or false",
                "description": "Repeated matching answers",
                "template_key": "matching",
                "shuffle": "on",
                "items_json": json.dumps(
                    [
                        {
                            "prompt": "The Earth is round",
                            "points": 10,
                            "options": [
                                {"text": "Верно", "is_correct": True},
                                {"text": "Неверно", "is_correct": False},
                            ],
                        },
                        {
                            "prompt": "Water freezes at zero degrees",
                            "points": 10,
                            "options": [
                                {"text": "верно", "is_correct": True},
                                {"text": "неверно", "is_correct": False},
                            ],
                        },
                    ],
                    ensure_ascii=False,
                ),
                "items_text": "",
                "action": "publish",
            },
        )

        self.assertEqual(response.status_code, 302)
        activity = Activity.objects.get(title="True or false")
        self.assertEqual(activity.status, Activity.Status.PUBLISHED)
        self.assertFalse(activity.config_json["correct_answers_only"])
        self.assertEqual(
            [item["options"][0]["text"] for item in activity.config_json["items"]],
            ["Верно", "верно"],
        )

    def test_matching_editor_saves_correct_answers_only_setting(self):
        response = self.client.post(
            reverse("activities:create"),
            {
                "title": "Correct choices only",
                "description": "Matching bank setting",
                "template_key": "matching",
                "correct_answers_only": "on",
                "items_json": json.dumps(
                    [
                        {
                            "prompt": "2 + 2",
                            "points": 10,
                            "options": [
                                {"text": "4", "is_correct": True},
                                {"text": "5", "is_correct": False},
                            ],
                        }
                    ]
                ),
                "items_text": "",
                "action": "save_draft",
            },
        )

        self.assertEqual(response.status_code, 302)
        activity = Activity.objects.get(title="Correct choices only")
        self.assertTrue(activity.config_json["correct_answers_only"])

    def test_switching_template_preserves_disabled_scoring_setting(self):
        response = self.client.post(
            reverse("activities:create"),
            {
                "title": "Switch score mode",
                "description": "Keep score mode",
                "template_key": "matching",
                "disable_scoring": "on",
                "items_json": json.dumps(
                    [
                        {
                            "prompt": "Python creator",
                            "points": 42,
                            "options": [
                                {"text": "Guido", "is_correct": True},
                                {"text": "Dennis", "is_correct": False},
                            ],
                        }
                    ]
                ),
                "items_text": "",
                "action": "switch_template",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["config_form"]["disable_scoring"].value())
        self.assertContains(response, 'data-default-points="10"', html=False)

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

        self.assertRedirects(response, f"{reverse('activities:edit', args=[activity.pk])}?tab=publish")
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
        self.assertContains(response, "quiz-flow")
        self.assertContains(response, "quiz-stage")
        self.assertContains(response, "Интерактив Quizzart")
        self.assertContains(response, "Гость")
        self.assertNotContains(response, "Режим учителя")
        self.assertNotContains(response, "Предпросмотр шаблона")

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
                    },
                    {
                        "id": "item-2",
                        "prompt": "Water formula?",
                        "points": 200,
                        "options": [
                            {"id": "a", "text": "H2O", "is_correct": True},
                            {"id": "b", "text": "CO2", "is_correct": False},
                        ],
                    }
                ],
            },
        )

        runtime = registry.get("choose_a_box").build_runtime_data(activity, preview=True)

        self.assertFalse(runtime["reveal_correct_answer"])
        self.assertEqual(runtime["boxes"][0]["number"], 1)
        self.assertEqual(runtime["boxes"][1]["number"], 2)
        self.assertEqual(len(runtime["boxes"]), 2)
        self.assertEqual(runtime["total_count"], 2)

    def test_choose_a_box_preview_renders_gift_cover_and_inline_panels(self):
        activity = Activity.objects.create(
            owner=self.user,
            title="Boxes preview shell",
            description="Preview the box flow",
            template_key="choose_a_box",
            config_json={
                "no_repeat": True,
                "reveal_correct_answer": True,
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

        response = self.client.get(reverse("activities:preview", args=[activity.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "box-gift.png")
        self.assertContains(response, "data-box-cover")
        # The preview uses the student's markup: one open form and one answer form per box.
        self.assertContains(response, "data-box-open-form", count=1)
        self.assertContains(response, "data-box-question-panel", count=1)
        self.assertContains(response, "data-preview-complete")
        self.assertNotContains(response, "data-preview-open-box")
        self.assertNotContains(response, "data-correct-option")
        self.assertNotContains(response, "правой колонке")

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
        self.assertContains(response, "data-wheel-background-frame")
        self.assertContains(response, "wheel-lights")
        self.assertContains(response, 'class="wheel-light"', count=24)
        self.assertContains(response, "Largest ocean?")

    def test_wheel_runtime_uses_ping_pong_palette_sequence(self):
        activity = Activity(
            title="Wheel palette",
            template_key="wheel_of_fortune",
            config_json={
                "items": [
                    {
                        "id": f"item-{index}",
                        "prompt": f"Question {index}",
                        "points": index * 100,
                        "options": [
                            {"id": "a", "text": "Correct", "is_correct": True},
                            {"id": "b", "text": "Wrong", "is_correct": False},
                        ],
                    }
                    for index in range(1, 7)
                ]
            },
        )

        runtime = registry.get("wheel_of_fortune").build_runtime_data(activity, preview=True)

        self.assertEqual(
            [sector["fill"] for sector in runtime["sectors"]],
            ["#c11755", "#aa7af1", "#ff9368", "#7d44c8", "#62bdf5", "#7d44c8"],
        )

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
            ["matching-choice-1", "matching-choice-2"],
        )
        self.assertCountEqual(
            [choice["text"] for choice in matching_runtime["answer_bank"]],
            ["Guido", "Dennis"],
        )
        self.assertTrue(matching_runtime["reveal_correct_answer"])
        # The right card stays on the server until the row is answered.
        self.assertNotIn("correct_choice_id", matching_runtime["rows"][0])
        definition = registry.get("matching")
        config = matching_activity.config_json
        item = definition.get_item(config, "item-1")
        feedback = definition.build_answer_feedback(config, item, definition.check_answer(config, item, "Dennis"))
        self.assertEqual(feedback["correct_choice_id"], "matching-choice-1")

    def test_matching_runtime_deduplicates_answers_case_insensitively(self):
        matching_activity = Activity(
            title="True or false preview",
            template_key="matching",
            config_json={
                "shuffle": False,
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "First statement",
                        "points": 10,
                        "options": [
                            {"id": "a", "text": "Верно", "is_correct": True},
                            {"id": "b", "text": "Неверно", "is_correct": False},
                        ],
                    },
                    {
                        "id": "item-2",
                        "prompt": "Second statement",
                        "points": 10,
                        "options": [
                            {"id": "c", "text": "  верно  ", "is_correct": True},
                            {"id": "d", "text": "НЕВЕРНО", "is_correct": False},
                        ],
                    },
                ],
            },
        )

        runtime = registry.get("matching").build_runtime_data(matching_activity, preview=True)

        self.assertEqual(
            runtime["answer_bank"],
            [
                {"id": "matching-choice-1", "text": "Верно"},
                {"id": "matching-choice-2", "text": "Неверно"},
            ],
        )
        definition = registry.get("matching")
        config = matching_activity.config_json
        self.assertEqual(
            [
                definition.build_answer_feedback(config, item, definition.check_answer(config, item, "Неверно"))[
                    "correct_choice_id"
                ]
                for item in definition.get_items(config)
            ],
            ["matching-choice-1", "matching-choice-1"],
        )

    def test_matching_runtime_can_keep_only_unique_correct_answers(self):
        matching_activity = Activity(
            title="Correct answers only preview",
            template_key="matching",
            config_json={
                "shuffle": False,
                "correct_answers_only": True,
                "items": [
                    {
                        "id": "item-1",
                        "prompt": "First statement",
                        "points": 10,
                        "options": [
                            {"id": "a", "text": "Верно", "is_correct": True},
                            {"id": "b", "text": "Лишний вариант", "is_correct": False},
                        ],
                    },
                    {
                        "id": "item-2",
                        "prompt": "Second statement",
                        "points": 10,
                        "options": [
                            {"id": "c", "text": "верно", "is_correct": False},
                            {"id": "d", "text": "Неверно", "is_correct": True},
                        ],
                    },
                ],
            },
        )

        runtime = registry.get("matching").build_runtime_data(matching_activity, preview=True)

        self.assertEqual(
            [choice["text"] for choice in runtime["answer_bank"]],
            ["Верно", "Неверно"],
        )

    def test_cards_runtime_is_deterministic_and_uses_card_collection(self):
        activity = Activity(
            title="Cards preview",
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
                    },
                    {
                        "id": "item-2",
                        "prompt": "Oak",
                        "points": 2,
                        "options": [
                            {"id": "a", "text": "Plants", "is_correct": True},
                            {"id": "b", "text": "Animals", "is_correct": False},
                        ],
                    },
                ],
            },
        )

        first_runtime = registry.get("categorize").build_runtime_data(activity, preview=True)
        second_runtime = registry.get("categorize").build_runtime_data(activity, preview=True)

        self.assertEqual([card["id"] for card in first_runtime["cards"]], [card["id"] for card in second_runtime["cards"]])
        self.assertEqual(len(first_runtime["cards"]), 2)
        self.assertTrue(first_runtime["reveal_correct_answer"])

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
                    },
                    {
                        "id": "item-2",
                        "prompt": "Oak",
                        "points": 2,
                        "options": [
                            {"id": "a", "text": "Plants", "is_correct": True},
                            {"id": "b", "text": "Animals", "is_correct": False},
                        ],
                    },
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
        self.assertContains(categorize_response, "data-categorize-board")
        self.assertContains(categorize_response, "data-categorize-card")
        self.assertContains(categorize_response, "data-categorize-card-inner")
        self.assertContains(categorize_response, "data-categorize-open")
        self.assertContains(categorize_response, "data-answer-form")
        self.assertContains(categorize_response, "cards-orange.png")
        self.assertContains(categorize_response, "cards-violet.png")
        self.assertContains(categorize_response, 'data-card-theme="orange"', html=False)
        self.assertContains(categorize_response, 'data-card-theme="violet"', html=False)
        self.assertContains(categorize_response, "Карточка 1")

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
        self.assertContains(response, "data-snake-dpad", html=False)
        self.assertContains(response, 'data-snake-direction="up"', html=False)
        self.assertContains(response, 'data-snake-direction="right"', html=False)
        self.assertContains(response, 'data-snake-direction="down"', html=False)
        self.assertContains(response, 'data-snake-direction="left"', html=False)


class EditorFixesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teacher-fixes", password="pass12345")
        self.client.force_login(self.user)

    def _post_quiz(self, items: list[dict], **extra):
        payload = {
            "title": "Quiz",
            "description": "",
            "template_key": "quiz",
            "items_json": json.dumps(items, ensure_ascii=False),
            "action": "save_draft",
        }
        payload.update(extra)
        return self.client.post(reverse("activities:create"), payload)

    @staticmethod
    def _item(points=10, options=None):
        return {
            "prompt": "2+2?",
            "points": points,
            "options": options or [{"text": "4", "is_correct": True}, {"text": "5", "is_correct": False}],
        }

    def test_duplicate_requires_post(self):
        activity = Activity.objects.create(owner=self.user, title="Original", template_key="quiz", config_json={})

        response = self.client.get(reverse("activities:duplicate", kwargs={"pk": activity.pk}))

        self.assertEqual(response.status_code, 405)
        self.assertEqual(Activity.objects.count(), 1)
        response = self.client.post(reverse("activities:duplicate", kwargs={"pk": activity.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Activity.objects.count(), 2)

    def test_points_outside_range_are_rejected(self):
        for points in (-5, 1001):
            with self.subTest(points=points):
                response = self._post_quiz([self._item(points=points)])

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "баллы должны быть от 0 до 1000")
                self.assertFalse(Activity.objects.exists())

    def test_zero_points_are_kept(self):
        response = self._post_quiz([self._item(points=0)])

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Activity.objects.get().config_json["items"][0]["points"], 0)

    def test_superscript_digit_in_text_row_is_an_option_not_a_crash(self):
        response = self.client.post(
            reverse("activities:create"),
            {
                "title": "Quiz",
                "template_key": "quiz",
                "items_text": "2+2? | *4 | 5 | ²",
                "action": "save_draft",
            },
        )

        self.assertEqual(response.status_code, 302)
        options = Activity.objects.get().config_json["items"][0]["options"]
        self.assertEqual([option["text"] for option in options], ["4", "5", "²"])

    def test_repeated_option_text_is_rejected(self):
        response = self._post_quiz(
            [self._item(options=[{"text": "4", "is_correct": True}, {"text": " 4 ", "is_correct": False}])]
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "варианты ответа не должны повторяться")

    def test_save_returns_to_the_tab_it_was_made_from(self):
        response = self._post_quiz([self._item()], active_tab="content")

        activity = Activity.objects.get()
        edit_url = reverse("activities:edit", kwargs={"pk": activity.pk})
        self.assertRedirects(response, f"{edit_url}?tab=content")
        response = self.client.get(response["Location"])
        self.assertContains(response, 'data-active-tab="content"', html=False)

    def test_save_from_general_tab_has_no_tab_query(self):
        response = self._post_quiz([self._item()], active_tab="general")

        activity = Activity.objects.get()
        self.assertRedirects(response, reverse("activities:edit", kwargs={"pk": activity.pk}))

    def test_template_switch_does_not_need_a_title(self):
        response = self.client.post(
            reverse("activities:create"),
            {
                "title": "",
                "template_key": "matching",
                "items_json": json.dumps([self._item()]),
                "action": "switch_template",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "novalidate", html=False)
        self.assertEqual(response.context["template_definition"].metadata.key, "matching")

    def test_stepper_is_russian(self):
        response = self.client.get(reverse("activities:create"))

        self.assertContains(response, "Черновик")
        self.assertNotContains(response, "Configured")

    def test_preview_of_unknown_template_is_404(self):
        activity = Activity.objects.create(owner=self.user, title="Old", template_key="removed", config_json={})

        response = self.client.get(reverse("activities:preview", kwargs={"pk": activity.pk}))

        self.assertEqual(response.status_code, 404)


class StableQuestionIdTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teacher-ids", password="pass12345")
        self.client.force_login(self.user)

    @staticmethod
    def _item(prompt, item_id=None):
        item = {
            "prompt": prompt,
            "points": 10,
            "options": [{"text": f"{prompt} yes", "is_correct": True}, {"text": f"{prompt} no", "is_correct": False}],
        }
        if item_id is not None:
            item["id"] = item_id
        return item

    def _save(self, items, activity=None):
        url = reverse("activities:edit", args=[activity.pk]) if activity else reverse("activities:create")
        return self.client.post(
            url,
            {
                "title": "Ids",
                "template_key": "quiz",
                "items_json": json.dumps(items, ensure_ascii=False),
                "action": "save_draft",
            },
        )

    def _ids(self):
        return [item["id"] for item in Activity.objects.get(owner=self.user).config_json["items"]]

    def test_new_questions_get_random_ids_and_derived_option_ids(self):
        self._save([self._item("One"), self._item("Two")])

        ids = self._ids()
        self.assertTrue(all(item_id.startswith("q-") and len(item_id) == 14 for item_id in ids))
        self.assertEqual(len(set(ids)), 2)
        options = Activity.objects.get().config_json["items"][0]["options"]
        self.assertEqual([option["id"] for option in options], [f"{ids[0]}-option-1", f"{ids[0]}-option-2"])

    def test_editor_carries_ids_and_reordering_keeps_them(self):
        self._save([self._item("One"), self._item("Two")])
        activity = Activity.objects.get()
        first, second = self._ids()

        response = self.client.get(reverse("activities:edit", args=[activity.pk]))
        self.assertContains(response, first)
        self._save([self._item("Two edited", second), self._item("One", first), self._item("Three")], activity)

        ids = self._ids()
        self.assertEqual(ids[:2], [second, first])
        self.assertNotIn(ids[2], {first, second})

    def test_legacy_positional_ids_survive_an_edit(self):
        activity = Activity.objects.create(
            owner=self.user,
            title="Legacy",
            template_key="quiz",
            config_json={"items": [{**self._item("One"), "id": "item-1"}, {**self._item("Two"), "id": "item-2"}]},
        )

        self._save([self._item("One", "item-1"), self._item("Two", "item-2")], activity)

        self.assertEqual(self._ids(), ["item-1", "item-2"])

    def test_old_editor_without_ids_reuses_ids_by_wording(self):
        self._save([self._item("One"), self._item("Two")])
        activity = Activity.objects.get()
        first, second = self._ids()

        self._save([self._item("Two"), self._item("New"), self._item("One")], activity)

        ids = self._ids()
        self.assertEqual((ids[0], ids[2]), (second, first))
        self.assertNotIn(ids[1], {first, second})

    def test_invalid_and_duplicate_ids_are_replaced(self):
        self._save([self._item("One", 'bad"id'), self._item("Two", "same"), self._item("Three", "same")])

        ids = self._ids()
        self.assertTrue(ids[0].startswith("q-"))
        self.assertEqual(ids[1], "same")
        self.assertNotEqual(ids[2], "same")

    def test_template_switch_and_duplicate_keep_ids(self):
        self._save([self._item("One"), self._item("Two")])
        activity = Activity.objects.get()
        ids = self._ids()

        response = self.client.post(
            reverse("activities:edit", args=[activity.pk]),
            {
                "title": "Ids",
                "template_key": "matching",
                "items_json": json.dumps([self._item("One", ids[0]), self._item("Two", ids[1])]),
                "action": "switch_template",
            },
        )
        self.assertContains(response, ids[0])

        self.client.post(reverse("activities:duplicate", args=[activity.pk]))
        copy = Activity.objects.exclude(pk=activity.pk).get()
        self.assertEqual([item["id"] for item in copy.config_json["items"]], ids)
