"""«Выбери коробку» on the per-answer protocol: a box opens on the server, every answer is checked on its own."""
from __future__ import annotations

import re

from django.urls import reverse

from attempts.models import ActivityAnswer, ActivitySession
from attempts.test_answers import AJAX, AnswerProtocolTestCase, question_bank


class ChooseABoxAnswerProtocolTests(AnswerProtocolTestCase):
    template_key = "choose_a_box"

    def open_box(self, link, item_key: str, *, ajax: bool = True):
        return self.client.post(
            f"/p/{link.slug}/",
            {"action": "open_box", "item_key": item_key},
            **(AJAX if ajax else {}),
        )

    def finish(self, link):
        return self.client.post(f"/p/{link.slug}/", {"action": "finish"})

    def play_page(self, link):
        return self.client.get(f"/p/{link.slug}/")

    def preview_page(self, link):
        return self.client.get(reverse("activities:preview", args=[link.activity.pk]))

    @staticmethod
    def box_states(response) -> dict[str, str]:
        return {box["id"]: box["state"] for box in response.context["runtime"]["boxes"]}

    @staticmethod
    def card_html(response, item_key: str) -> str:
        html = response.content.decode()
        cards = [chunk for chunk in html.split("<article")[1:] if f'data-item-id="{item_key}"' in chunk]
        assert len(cards) == 1, f"one card for {item_key}"
        return cards[0].split("</article>")[0]

    @staticmethod
    def finish_form_tag(response) -> str:
        match = re.search(r"<form[^>]*data-box-finish[^>]*>", response.content.decode())
        return match.group(0) if match else ""

    def assert_no_bulk_finish(self, response):
        html = response.content.decode()
        self.assertNotIn("data-box-finish-form", html)
        self.assertNotIn("data-box-answer-target", html)
        self.assertNotIn('name="box_', html)

    def test_player_and_preview_html_carry_no_answer_key(self):
        for reveal in (True, False):
            with self.subTest(reveal=reveal):
                link = self.publish(question_bank(3, reveal_correct_answer=reveal))
                self.start(link)

                page = self.play_page(link)
                self.assert_no_answer_key(page)
                self.assert_no_bulk_finish(page)
                runtime = page.context["runtime"]
                self.assertNotIn("review_items", runtime)
                self.assertNotIn("expected_answer", str(runtime["boxes"]))
                self.assertNotIn("correct_option", str(runtime["boxes"]))

                # An opened box shows its question and options, never which one is right.
                self.open_box(link, "q-1")
                self.assert_no_answer_key(self.play_page(link))

                self.client.force_login(self.teacher)
                preview = self.preview_page(link)
                self.assert_no_answer_key(preview)
                self.assert_no_bulk_finish(preview)
                self.assertNotIn("review_items", preview.context["runtime"])
                self.client.logout()

    def test_play_and_preview_share_one_markup(self):
        link = self.publish(question_bank(2))
        self.start(link)
        page = self.play_page(link)
        self.client.force_login(self.teacher)
        preview = self.preview_page(link)

        for response in (page, preview):
            with self.subTest(preview=response is preview):
                self.assertContains(response, "data-box-open-form", count=2)
                self.assertContains(response, 'value="open_box"', count=2)
                self.assertContains(response, 'data-state="unopened"', count=2)
                # Options are submit buttons: a click, the keyboard and a page without JavaScript all work.
                buttons = re.findall(r'<button[^>]*name="answer"[^>]*>', response.content.decode())
                self.assertEqual(len(buttons), 4)
                self.assertTrue(all('type="submit"' in button for button in buttons))
                self.assertNotContains(response, 'type="radio"')
                self.assertNotContains(response, "data-preview-open-box")
                self.assertContains(response, 'aria-live="polite"')

        self.assertContains(page, f'data-action-url="/p/{link.slug}/"')
        self.assertContains(preview, f'data-action-url="{reverse("activities:preview_action", args=[link.activity.pk])}"')
        self.assertContains(preview, "data-preview-complete")
        self.assertNotContains(page, "data-preview-complete")
        self.assertEqual(self.finish_form_tag(preview), "")
        self.assertNotEqual(self.finish_form_tag(page), "")

    def test_open_box_is_saved_and_rendered_opened_after_a_reload(self):
        link = self.publish(question_bank(3))
        self.start(link)

        payload = self.open_box(link, "q-2").json()

        self.assertEqual((payload["ok"], payload["action"], payload["item_key"]), (True, "open_box", "q-2"))
        self.assertIsNone(payload["feedback"])
        self.assertEqual((payload["answered_count"], payload["total_count"], payload["is_complete"]), (0, 3, False))
        self.assertEqual(ActivitySession.objects.get().runtime_state["opened"], ["q-2"])

        page = self.play_page(link)
        self.assertEqual(self.box_states(page), {"q-1": "unopened", "q-2": "opened", "q-3": "unopened"})
        opened = self.card_html(page, "q-2")
        self.assertIn("data-box-cover hidden", opened)
        self.assertIn("data-box-question-panel>", opened)
        self.assertIn("Question 2?", opened)
        closed = self.card_html(page, "q-1")
        self.assertIn("data-box-cover>", closed)
        self.assertIn("data-box-question-panel hidden", closed)
        self.assertFalse(ActivityAnswer.objects.exists())

    def test_open_box_without_javascript_is_a_form_post(self):
        link = self.publish(question_bank(2))
        self.start(link)

        response = self.open_box(link, "q-1", ajax=False)
        self.open_box(link, "q-1", ajax=False)

        self.assertRedirects(response, f"/p/{link.slug}/")
        self.assertEqual(ActivitySession.objects.get().runtime_state["opened"], ["q-1"])
        self.assertEqual(self.box_states(self.play_page(link))["q-1"], "opened")

    def test_answer_json_flow_and_reveal_policy(self):
        for reveal, expected_correct, feedback_text in (
            (True, "ZZCORRECT 1", "Неверно. Правильный ответ: ZZCORRECT 1"),
            (False, None, "Неверно."),
        ):
            with self.subTest(reveal=reveal):
                link = self.publish(question_bank(2, reveal_correct_answer=reveal))
                self.start(link)
                self.open_box(link, "q-1")

                payload = self.answer(link, "q-1", "ZZWRONG 1").json()

                self.assertEqual(
                    payload["feedback"],
                    {"submitted": "ZZWRONG 1", "is_correct": False, "correct_option": expected_correct, "score_awarded": 0},
                )
                self.assertEqual((payload["answered_count"], payload["total_count"]), (1, 2))
                self.assertEqual((payload["score"], payload["max_score"]), (0, 20))
                self.assertFalse(payload["is_complete"])
                self.assertIsNone(payload["redirect_url"])

                page = self.play_page(link)
                self.assertEqual(self.box_states(page), {"q-1": "answered", "q-2": "unopened"})
                answered = self.card_html(page, "q-1")
                self.assertIn(feedback_text, answered)
                self.assertEqual(answered.count("disabled"), 2)
                self.assertIn("is-wrong", answered)

    def test_last_answer_completes_the_run(self):
        link = self.publish(question_bank(2))
        self.start(link)
        self.answer(link, "q-1", "ZZCORRECT 1")

        payload = self.answer(link, "q-2", "ZZWRONG 2").json()

        self.assertTrue(payload["is_complete"])
        self.assertEqual(payload["redirect_url"], f"/p/{link.slug}/results/")
        session = ActivitySession.objects.get()
        self.assertEqual((session.status, session.score, session.max_score), ("completed", 10, 20))
        self.assertEqual(self.client.get(f"/p/{link.slug}/results/").status_code, 200)

    def test_finish_is_offered_after_the_first_answer(self):
        link = self.publish(question_bank(3))
        self.start(link)
        self.assertIn("hidden", self.finish_form_tag(self.play_page(link)))

        self.open_box(link, "q-1")
        self.assertIn("hidden", self.finish_form_tag(self.play_page(link)))

        self.answer(link, "q-1", "ZZWRONG 1")
        tag = self.finish_form_tag(self.play_page(link))
        self.assertNotIn("hidden", tag)
        self.assertIn('method="post"', tag)

    def test_early_finish_after_one_answer_completes_with_that_score(self):
        link = self.publish(question_bank(3))
        self.start(link)
        self.open_box(link, "q-1")
        self.answer(link, "q-1", "ZZCORRECT 1")
        self.open_box(link, "q-2")

        response = self.finish(link)

        self.assertRedirects(response, f"/p/{link.slug}/results/")
        session = ActivitySession.objects.get()
        self.assertEqual(session.status, ActivitySession.Status.COMPLETED)
        self.assertEqual((session.score, session.max_score), (10, 30))
        self.assertEqual(list(session.answers.values_list("item_key", flat=True)), ["q-1"])

    def test_a_reload_resumes_the_board(self):
        link = self.publish(question_bank(3))
        self.start(link)
        self.answer(link, "q-1", "ZZCORRECT 1", ajax=False)
        self.open_box(link, "q-2", ajax=False)

        page = self.play_page(link)

        self.assertEqual(self.box_states(page), {"q-1": "answered", "q-2": "opened", "q-3": "unopened"})
        runtime = page.context["runtime"]
        self.assertEqual((runtime["answered_count"], runtime["total_count"]), (1, 3))
        self.assertIn("Верно. Ответ засчитан.", self.card_html(page, "q-1"))
        self.assertContains(page, "1 из 3")
        # The saved answer is final after a reload too.
        again = self.answer(link, "q-1", "ZZWRONG 1").json()
        self.assertTrue(again["already_answered"])
        self.assertEqual(again["feedback"]["submitted"], "ZZCORRECT 1")
        self.assertEqual(ActivitySession.objects.get().score, 10)

    def test_unknown_choice_or_box_is_rejected(self):
        link = self.publish(question_bank(2))
        self.start(link)
        self.open_box(link, "q-1")

        for item_key, answer in (("q-1", "made up"), ("q-1", ""), ("q-1", "ZZCORRECT 2"), ("missing", "ZZCORRECT 1")):
            with self.subTest(item_key=item_key, answer=answer):
                response = self.answer(link, item_key, answer)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()["ok"])

        response = self.open_box(link, "missing")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ActivityAnswer.objects.exists())
        self.assertEqual(ActivitySession.objects.get().runtime_state["opened"], ["q-1"])

    def test_preview_checks_answers_and_opens_boxes_in_the_page(self):
        link = self.publish(question_bank(2))
        url = reverse("activities:preview_action", args=[link.activity.pk])
        self.client.force_login(self.teacher)

        answer = self.client.post(url, {"action": "answer", "item_key": "q-1", "answer": "ZZCORRECT 1"})
        opened = self.client.post(url, {"action": "open_box", "item_key": "q-1"})

        self.assertEqual(answer.json()["feedback"]["is_correct"], True)
        self.assertEqual(opened.status_code, 400)
        self.assertFalse(ActivitySession.objects.exists())
        self.assertFalse(ActivityAnswer.objects.exists())
