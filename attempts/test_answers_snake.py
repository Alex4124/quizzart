"""The snake on the per-answer protocol: every eaten apple's answer is checked on the server."""
from __future__ import annotations

import re

from django.urls import reverse

from attempts.models import ActivityAnswer, ActivitySession
from attempts.test_answers import AnswerProtocolTestCase, question_bank


def apple_tag(html: str, item_key: str) -> str:
    match = re.search(rf'<div\s+class="snake-apple"[^>]*data-item-id="{re.escape(item_key)}"[^>]*>', html)
    return match.group(0) if match else ""


def question_card_tag(html: str, item_key: str) -> str:
    match = re.search(rf'<article\s+class="card snake-question-card"[^>]*data-item-id="{re.escape(item_key)}"[^>]*>', html)
    return match.group(0) if match else ""


class SnakeAnswerProtocolTests(AnswerProtocolTestCase):
    template_key = "snake"

    def assert_runtime_has_no_answer_key(self, runtime: dict):
        self.assertNotIn("review_items", runtime)
        for apple in runtime["apples"]:
            self.assertNotIn("correct_option", apple)
            self.assertIsNone(apple["feedback"])

    def test_player_and_preview_html_carry_no_answer_key(self):
        for reveal in (True, False):
            with self.subTest(reveal=reveal):
                link = self.publish(question_bank(3, reveal_correct_answer=reveal))
                self.start(link)
                page = self.client.get(f"/p/{link.slug}/")
                self.assert_no_answer_key(page)
                self.assert_runtime_has_no_answer_key(page.context["runtime"])
                self.assertNotContains(page, "data-snake-submit-form")
                self.assertNotContains(page, 'name="question_')

                self.client.force_login(self.teacher)
                preview = self.client.get(reverse("activities:preview", args=[link.activity.pk]))
                self.assert_no_answer_key(preview)
                self.assert_runtime_has_no_answer_key(preview.context["runtime"])
                self.assertContains(
                    preview,
                    f'data-action-url="{reverse("activities:preview_action", args=[link.activity.pk])}"',
                )
                self.assertContains(preview, "data-preview-complete")
                self.client.logout()

    def test_every_apple_is_a_form_with_option_buttons(self):
        link = self.publish(question_bank(2))
        self.start(link)

        page = self.client.get(f"/p/{link.slug}/")

        self.assertContains(page, 'data-player-root', count=1)
        self.assertContains(page, f'data-action-url="/p/{link.slug}/"')
        self.assertContains(page, 'data-total-count="2"')
        self.assertContains(page, 'name="action" value="answer"', count=2)
        self.assertContains(page, 'name="item_key" value="q-1"', count=1)
        html = page.content.decode()
        for option in ("ZZCORRECT 1", "ZZWRONG 1", "ZZCORRECT 2", "ZZWRONG 2"):
            self.assertRegex(html, rf'<button[^>]*type="submit"\s+name="answer"\s+value="{option}"')
        self.assertContains(page, 'data-question-feedback aria-live="polite"', count=2)
        self.assertEqual((page.context["runtime"]["answered_count"], page.context["runtime"]["total_count"]), (0, 2))

    def test_answer_json_flow_to_the_results(self):
        for reveal, expected_correct in ((True, "ZZCORRECT 1"), (False, None)):
            with self.subTest(reveal=reveal):
                link = self.publish(question_bank(2, reveal_correct_answer=reveal))
                self.start(link)

                first = self.answer(link, "q-1", "ZZWRONG 1").json()

                self.assertEqual(
                    first["feedback"],
                    {"submitted": "ZZWRONG 1", "is_correct": False, "correct_option": expected_correct, "score_awarded": 0},
                )
                self.assertEqual((first["answered_count"], first["total_count"]), (1, 2))
                self.assertEqual((first["score"], first["max_score"]), (0, 20))
                self.assertFalse(first["is_complete"])
                self.assertIsNone(first["redirect_url"])

                last = self.answer(link, "q-2", "ZZCORRECT 2").json()

                self.assertEqual(last["feedback"]["is_correct"], True)
                self.assertEqual((last["answered_count"], last["score"]), (2, 10))
                self.assertTrue(last["is_complete"])
                self.assertEqual(last["redirect_url"], f"/p/{link.slug}/results/")
                session = ActivitySession.objects.get(share_link=link)
                self.assertEqual((session.status, session.score), (ActivitySession.Status.COMPLETED, 10))

    def test_reload_after_an_answer_without_javascript_keeps_the_apple_eaten(self):
        link = self.publish(question_bank(3))
        self.start(link)

        response = self.answer(link, "q-1", "ZZCORRECT 1", ajax=False)

        self.assertRedirects(response, f"/p/{link.slug}/")
        page = self.client.get(f"/p/{link.slug}/")
        html = page.content.decode()
        runtime = page.context["runtime"]
        self.assertEqual((runtime["answered_count"], runtime["total_count"]), (1, 3))
        self.assertEqual([apple["is_answered"] for apple in runtime["apples"]], [True, False, False])
        self.assertIn('data-eaten="1" hidden', apple_tag(html, "q-1"))
        self.assertNotIn("data-eaten", apple_tag(html, "q-2"))
        self.assertIn('data-state="answered"', question_card_tag(html, "q-1"))
        self.assertIn('data-state="open"', question_card_tag(html, "q-2"))
        self.assertContains(page, "<strong data-snake-progress>1</strong>/3", html=False)
        self.assertContains(page, "<strong data-snake-remaining>2</strong>", html=False)
        self.assertContains(page, "<strong data-snake-score>10</strong>", html=False)
        self.assertContains(page, "Верно. Ответ засчитан.")

    def test_unknown_choice_is_rejected(self):
        link = self.publish(question_bank(2))
        self.start(link)

        response = self.answer(link, "q-1", "made up")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertFalse(ActivityAnswer.objects.exists())

    def test_first_eaten_apple_answer_is_final(self):
        link = self.publish(question_bank(2))
        self.start(link)
        self.answer(link, "q-1", "ZZWRONG 1")

        payload = self.answer(link, "q-1", "ZZCORRECT 1").json()

        self.assertTrue(payload["already_answered"])
        self.assertEqual(payload["feedback"]["submitted"], "ZZWRONG 1")
        self.assertEqual(ActivitySession.objects.get().score, 0)

    def test_legacy_partial_submit_is_still_rejected(self):
        link = self.publish(question_bank(2))
        self.start(link)

        response = self.client.post(
            f"/p/{link.slug}/",
            {"action": "submit_snake", "question_q-1": "ZZCORRECT 1"},
            follow=True,
        )

        self.assertContains(response, "Ответьте на все задания")
        session = ActivitySession.objects.get()
        self.assertEqual(session.status, ActivitySession.Status.STARTED)
        self.assertFalse(session.answers.exists())

    def test_legacy_submit_counts_apples_answered_one_by_one(self):
        link = self.publish(question_bank(2))
        self.start(link)
        self.answer(link, "q-1", "ZZWRONG 1")

        response = self.client.post(f"/p/{link.slug}/", {"action": "submit_snake", "question_q-2": "ZZCORRECT 2"})

        self.assertRedirects(response, f"/p/{link.slug}/results/")
        session = ActivitySession.objects.get()
        self.assertEqual((session.status, session.score), (ActivitySession.Status.COMPLETED, 10))
        self.assertFalse(session.answers.get(item_key="q-1").is_correct)

    def test_preview_checks_an_apple_without_saving(self):
        link = self.publish(question_bank(2))
        self.client.force_login(self.teacher)

        response = self.client.post(
            reverse("activities:preview_action", args=[link.activity.pk]),
            {"action": "answer", "item_key": "q-2", "answer": "ZZCORRECT 2"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["feedback"]["is_correct"], True)
        self.assertFalse(ActivitySession.objects.exists())
