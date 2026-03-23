from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase

from activities.models import Activity
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
            },
        )


class ActivityEditorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teacher", password="pass12345")

    def test_teacher_can_create_choose_a_box_draft(self):
        self.client.login(username="teacher", password="pass12345")
        response = self.client.post(
            "/activities/new/",
            {
                "title": "Boxes",
                "description": "Practice",
                "template_key": "choose_a_box",
                "grid_size": "6",
                "no_repeat": "on",
                "boxes_text": "\n".join(
                    [
                        "100 | Q1 | A1 | 100",
                        "200 | Q2 | A2 | 200",
                        "300 | Q3 | A3 | 300",
                        "400 | Q4 | A4 | 400",
                        "500 | Q5 | A5 | 500",
                        "600 | Q6 | A6 | 600",
                    ]
                ),
                "action": "save_draft",
            },
        )
        self.assertEqual(response.status_code, 302)
        activity = Activity.objects.get(title="Boxes")
        self.assertEqual(activity.status, Activity.Status.DRAFT)
        self.assertEqual(activity.template_key, "choose_a_box")
