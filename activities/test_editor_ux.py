from __future__ import annotations

import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from activities.models import Activity
from activities.services import ensure_share_link
from interactive_templates.registry import registry
from interactive_templates.utils import QuestionBankErrors, parse_question_bank_editor_json


def _question(prompt="2+2?", options=None, points=10, item_id=None):
    item = {
        "prompt": prompt,
        "points": points,
        "options": options or [{"text": f"{prompt} yes", "is_correct": True}, {"text": f"{prompt} no", "is_correct": False}],
    }
    if item_id is not None:
        item["id"] = item_id
    return item


class QuestionBankErrorsTests(TestCase):
    """The bank is checked as a whole: every question's problems come back at once, tied to its card."""

    def setUp(self):
        self.user = User.objects.create_user(username="teacher-errors", password="pass12345")
        self.client.force_login(self.user)

    def _post(self, items, **extra):
        payload = {
            "title": "Quiz",
            "template_key": "quiz",
            "items_json": json.dumps(items, ensure_ascii=False),
            "items_text": "",
            "action": "save_draft",
            "active_tab": "content",
        }
        payload.update(extra)
        return self.client.post(reverse("activities:create"), payload)

    def _broken_bank(self):
        return [
            _question(prompt=""),
            _question("Fine"),
            _question("One answer", options=[{"text": "Only", "is_correct": True}, {"text": "", "is_correct": False}]),
            _question(
                "Many problems",
                points=2000,
                options=[
                    {"text": "Same", "is_correct": True},
                    {"text": " same ", "is_correct": True},
                ],
            ),
        ]

    def test_every_question_error_is_reported_with_its_number(self):
        response = self._post(self._broken_bank())

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Activity.objects.exists())
        self.assertEqual(
            response.context["config_form"].non_field_errors(),
            [
                "Вопрос 1: заполните текст вопроса.",
                "Вопрос 3: должно быть минимум два заполненных ответа.",
                "Вопрос 4: должен быть ровно один отмеченный правильный ответ.",
                "Вопрос 4: варианты ответа не должны повторяться («same»).",
                "Вопрос 4: баллы должны быть от 0 до 1000.",
            ],
        )
        self.assertEqual(response.context["active_tab"], "content")

    def test_question_errors_reach_the_template_per_card(self):
        response = self._post(self._broken_bank())

        self.assertEqual(
            response.context["question_errors"],
            {
                1: ["Заполните текст вопроса."],
                3: ["Должно быть минимум два заполненных ответа."],
                4: [
                    "Должен быть ровно один отмеченный правильный ответ.",
                    "Варианты ответа не должны повторяться («same»).",
                    "Баллы должны быть от 0 до 1000.",
                ],
            },
        )
        self.assertContains(response, '<script id="question-bank-errors" type="application/json">', html=False)
        self.assertContains(response, "data-unsaved-post", html=False)

    def test_a_valid_page_has_no_question_errors(self):
        response = self.client.get(reverse("activities:create"))

        self.assertEqual(response.context["question_errors"], {})
        self.assertNotContains(response, "question-bank-errors")
        self.assertNotContains(response, "data-unsaved-post")

    def test_numbers_follow_the_cards_even_when_an_empty_card_is_skipped(self):
        empty = {"prompt": "", "points": 10, "options": [{"text": "", "is_correct": True}, {"text": "", "is_correct": False}]}
        response = self._post([empty, _question(prompt="", options=[{"text": "a", "is_correct": True}, {"text": "b"}])])

        self.assertEqual(list(response.context["question_errors"]), [2])
        self.assertContains(response, "Вопрос 2: заполните текст вопроса.")

    def test_an_all_empty_bank_still_asks_for_a_question(self):
        empty = {"prompt": "", "points": 10, "options": [{"text": "", "is_correct": True}, {"text": "", "is_correct": False}]}
        response = self._post([empty])

        self.assertContains(response, "Добавьте хотя бы один вопрос.")
        self.assertEqual(response.context["question_errors"], {})

    def test_title_and_question_errors_are_shown_together(self):
        response = self._post([_question(prompt="")], title="")

        self.assertTrue(response.context["activity_form"]["title"].errors)
        self.assertEqual(response.context["question_errors"], {1: ["Заполните текст вопроса."]})
        self.assertEqual(response.context["active_tab"], "general")

    def test_parser_raises_one_error_with_every_question(self):
        with self.assertRaises(QuestionBankErrors) as caught:
            parse_question_bank_editor_json(
                json.dumps([_question(points=-1), _question("Ok"), _question(prompt="", options=[{"text": "x"}])])
            )

        self.assertEqual(
            caught.exception.question_errors,
            {
                1: ["баллы должны быть от 0 до 1000."],
                3: [
                    "заполните текст вопроса.",
                    "должно быть минимум два заполненных ответа.",
                    "должен быть ровно один отмеченный правильный ответ.",
                ],
            },
        )
        self.assertEqual(caught.exception.messages[0], "Вопрос 1: баллы должны быть от 0 до 1000.")

    def test_percent_sign_in_an_answer_does_not_break_the_message(self):
        response = self._post(
            [_question("Share?", options=[{"text": "50%", "is_correct": True}, {"text": "50%", "is_correct": False}])]
        )

        self.assertContains(response, "Вопрос 1: варианты ответа не должны повторяться («50%»).")

    def test_text_payload_still_validates(self):
        response = self.client.post(
            reverse("activities:create"),
            {
                "title": "Text quiz",
                "template_key": "quiz",
                "items_text": "Fine? | *a | b\nBroken | *x\nPoints? | *a | b | 5000",
                "action": "save_draft",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Строка 2 должна содержать вопрос и минимум два варианта ответа.")
        self.assertEqual(response.context["question_errors"], {})
        self.assertFalse(Activity.objects.exists())

        response = self.client.post(
            reverse("activities:create"),
            {
                "title": "Text quiz",
                "template_key": "quiz",
                "items_text": "Fine? | *a | b\nSecond? | x | *y | 25",
                "action": "save_draft",
            },
        )

        self.assertEqual(response.status_code, 302)
        items = Activity.objects.get().config_json["items"]
        self.assertEqual([item["points"] for item in items], [10, 25])
        self.assertTrue(all(item["id"].startswith("q-") for item in items))


class QuestionActionsIdTests(TestCase):
    """What the editor posts after «Вверх»/«Вниз», «Дублировать», «Удалить» + «Отменить» and «Вставить списком»."""

    def setUp(self):
        self.user = User.objects.create_user(username="teacher-actions", password="pass12345")
        self.client.force_login(self.user)
        self.client.post(
            reverse("activities:create"),
            {
                "title": "Ids",
                "template_key": "quiz",
                "items_json": json.dumps([_question("One"), _question("Two"), _question("Three")]),
                "action": "save_draft",
            },
        )
        self.activity = Activity.objects.get()
        self.ids = self._ids()

    def _ids(self):
        self.activity.refresh_from_db()
        return [item["id"] for item in self.activity.config_json["items"]]

    def _save(self, items):
        return self.client.post(
            reverse("activities:edit", args=[self.activity.pk]),
            {
                "title": "Ids",
                "template_key": "quiz",
                "items_json": json.dumps(items, ensure_ascii=False),
                "action": "save_changes",
            },
        )

    def test_moved_questions_keep_their_ids(self):
        one, two, three = self.ids

        self._save([_question("Two", item_id=two), _question("Three", item_id=three), _question("One", item_id=one)])

        self.assertEqual(self._ids(), [two, three, one])

    def test_a_duplicate_gets_a_fresh_id_and_the_same_answers(self):
        one, two, three = self.ids
        copy = {**_question("One"), "id": ""}

        self._save([_question("One", item_id=one), copy, _question("Two", item_id=two), _question("Three", item_id=three)])

        ids = self._ids()
        self.assertEqual([ids[0], ids[2], ids[3]], [one, two, three])
        self.assertNotIn(ids[1], {one, two, three})
        self.assertTrue(ids[1].startswith("q-"))
        items = self.activity.config_json["items"]
        self.assertEqual(
            [option["text"] for option in items[1]["options"]],
            [option["text"] for option in items[0]["options"]],
        )
        self.assertEqual([option["id"] for option in items[1]["options"]], [f"{ids[1]}-option-1", f"{ids[1]}-option-2"])

    def test_deleting_a_question_drops_only_its_id_and_undo_keeps_it(self):
        one, two, three = self.ids

        self._save([_question("One", item_id=one), _question("Three", item_id=three)])
        self.assertEqual(self._ids(), [one, three])

        # «Отменить» puts the very same card back: the editor posts its id again.
        self._save([_question("One", item_id=one), _question("Two", item_id=two), _question("Three", item_id=three)])
        self.assertEqual(self._ids(), [one, two, three])

    def test_pasted_questions_are_new(self):
        one, two, three = self.ids

        self._save(
            [
                _question("One", item_id=one),
                _question("Two", item_id=two),
                _question("Three", item_id=three),
                _question("Pasted", points=25, item_id=""),
            ]
        )

        ids = self._ids()
        self.assertEqual(ids[:3], [one, two, three])
        self.assertTrue(ids[3].startswith("q-"))
        self.assertEqual(self.activity.config_json["items"][3]["points"], 25)


class EditorMarkupTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="teacher-markup", password="pass12345")
        self.client.force_login(self.user)

    def _activity(self, published=False):
        activity = Activity.objects.create(
            owner=self.user,
            title="Markup",
            template_key="quiz",
            config_json=registry.get("quiz").default_config(),
        )
        if published:
            activity.publish()
            activity.save()
            ensure_share_link(activity)
        return activity

    def test_answer_template_uses_a_radio_with_its_own_label(self):
        response = self.client.get(reverse("activities:create"))

        self.assertContains(response, '<input type="radio" data-answer-correct>', html=False)
        self.assertNotContains(response, 'type="checkbox" data-answer-correct')
        self.assertContains(response, '<label class="editor-cell-label" data-answer-title></label>', html=False)

    def test_tabs_and_template_cards_are_accessible(self):
        response = self.client.get(reverse("activities:create"))

        self.assertContains(response, 'role="tablist"', html=False)
        self.assertContains(response, 'role="tab"', count=4, html=False)
        self.assertContains(response, 'role="tabpanel"', count=4, html=False)
        self.assertContains(response, 'aria-controls="tab-content"', html=False)
        self.assertContains(response, 'aria-labelledby="editor-tab-content"', html=False)
        self.assertContains(response, 'aria-selected="true"', count=1, html=False)
        self.assertNotContains(response, 'role="list"', html=False)
        self.assertContains(response, 'aria-pressed="true"', count=1, html=False)

    def test_bulk_import_dialog_shows_the_format(self):
        response = self.client.get(reverse("activities:create"))

        self.assertContains(response, "Вставить списком")
        self.assertContains(response, "data-bulk-dialog", html=False)
        self.assertContains(response, "<code>Вопрос | *Правильный ответ | Неверный 1 | Неверный 2 | необязательные баллы</code>", html=False)

    def test_preview_thumbnail_waits_for_the_script(self):
        activity = self._activity()

        response = self.client.get(reverse("activities:edit", args=[activity.pk]))

        preview_url = reverse("activities:preview", args=[activity.pk])
        self.assertContains(response, f'data-src="{preview_url}"', html=False)
        self.assertNotRegex(response.content.decode(), rf'(?<!data-)src="{preview_url}"')
        self.assertContains(response, 'width="1280"', html=False)
        self.assertContains(response, "inert", html=False)

    def test_copy_link_buttons_only_for_a_published_activity(self):
        draft = self._activity()
        response = self.client.get(reverse("activities:edit", args=[draft.pk]))
        self.assertNotContains(response, "data-copy-link=", html=False)
        self.assertContains(response, "data-copy-toast", html=False)

        published = self._activity(published=True)
        response = self.client.get(reverse("activities:edit", args=[published.pk]))
        share_url = response.context["share_url"]
        self.assertTrue(share_url)
        self.assertContains(response, f'data-copy-link="{share_url}"', count=2, html=False)
        self.assertContains(response, "Скопировать ссылку", count=2)
