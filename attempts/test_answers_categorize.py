"""Cards («Карточки») on the per-answer protocol: one card, one answer, checked on the server."""
from __future__ import annotations

from django.urls import reverse

from attempts.models import ActivityAnswer, ActivitySession
from attempts.test_answers import AnswerProtocolTestCase, question_bank


def summary_value(page, key: str) -> str:
    return next(card["value"] for card in page.context["player_shell"]["summary_cards"] if card["key"] == key)


class CategorizeAnswerProtocolTests(AnswerProtocolTestCase):
    template_key = "categorize"

    def test_player_and_preview_html_carry_no_answer_key(self):
        for reveal in (True, False):
            with self.subTest(reveal=reveal):
                link = self.publish(question_bank(3, reveal_correct_answer=reveal, shuffle=True))
                self.start(link)

                page = self.client.get(f"/p/{link.slug}/")

                self.assert_no_answer_key(page)
                self.assertNotIn("review_items", page.context["runtime"])
                self.assertTrue(all(isinstance(option, str) for card in page.context["runtime"]["cards"] for option in card["options"]))

                self.client.force_login(self.teacher)
                self.assert_no_answer_key(self.client.get(reverse("activities:preview", args=[link.activity.pk])))
                self.client.logout()

    def test_every_card_is_its_own_answer_form(self):
        link = self.publish(question_bank(2))
        self.start(link)

        page = self.client.get(f"/p/{link.slug}/")

        self.assertContains(page, "data-answer-form", count=2)
        self.assertContains(page, "data-categorize-open", count=2)
        self.assertContains(page, '<input type="hidden" name="item_key" value="q-1">', html=True)
        self.assertContains(page, 'type="submit"', count=4)
        self.assertContains(page, 'aria-live="polite"', count=2)
        # The old page collected every answer in hidden inputs and posted the whole run at the end.
        self.assertNotContains(page, "submit_categorize")
        self.assertNotContains(page, 'name="question_')

    def test_answer_json_flow_to_the_results(self):
        link = self.publish(question_bank(2, reveal_correct_answer=True))
        self.start(link)

        first = self.answer(link, "q-1", "ZZWRONG 1").json()

        self.assertEqual(
            first["feedback"],
            {"submitted": "ZZWRONG 1", "is_correct": False, "correct_option": "ZZCORRECT 1", "score_awarded": 0},
        )
        self.assertEqual((first["answered_count"], first["total_count"]), (1, 2))
        self.assertEqual((first["score"], first["max_score"]), (0, 20))
        self.assertFalse(first["is_complete"])
        self.assertIsNone(first["redirect_url"])

        last = self.answer(link, "q-2", "ZZCORRECT 2").json()

        self.assertEqual(last["feedback"]["is_correct"], True)
        self.assertTrue(last["is_complete"])
        self.assertEqual(last["redirect_url"], f"/p/{link.slug}/results/")
        session = ActivitySession.objects.get()
        self.assertEqual((session.status, session.score), (ActivitySession.Status.COMPLETED, 10))

    def test_reveal_off_says_only_that_the_answer_is_saved(self):
        link = self.publish(question_bank(2, reveal_correct_answer=False))
        self.start(link)

        payload = self.answer(link, "q-1", "ZZWRONG 1").json()

        self.assertEqual(
            payload["feedback"],
            {"submitted": "ZZWRONG 1", "is_correct": None, "correct_option": None, "score_awarded": None},
        )
        self.assertIsNone(payload["score"])
        self.assertIsNone(payload["percent_score"])
        self.assertEqual(payload["max_score"], 20)

        page = self.client.get(f"/p/{link.slug}/")
        self.assert_no_answer_key(page)
        self.assertContains(page, "Ответ сохранён.")
        self.assertNotContains(page, "Неверно")
        self.assertEqual(summary_value(page, "score"), "—")

    def test_reload_after_an_answer_without_javascript_continues_the_run(self):
        link = self.publish(question_bank(3, reveal_correct_answer=True))
        self.start(link)

        response = self.answer(link, "q-2", "ZZCORRECT 2", ajax=False)

        self.assertRedirects(response, f"/p/{link.slug}/")
        page = self.client.get(f"/p/{link.slug}/")
        runtime = page.context["runtime"]
        self.assertEqual((runtime["answered_count"], runtime["total_count"]), (1, 3))
        answered = [card for card in runtime["cards"] if card["is_answered"]]
        self.assertEqual([card["id"] for card in answered], ["q-2"])
        self.assertEqual(answered[0]["feedback"]["submitted"], "ZZCORRECT 2")
        self.assertContains(page, 'data-state="answered"', count=1)
        self.assertContains(page, 'data-state="closed"', count=2)
        self.assertContains(page, "Верно. Ответ засчитан.")
        self.assertEqual(summary_value(page, "score"), "10")

        # The other cards still take answers, and the last one finishes the run.
        self.answer(link, "q-1", "ZZCORRECT 1", ajax=False)
        response = self.answer(link, "q-3", "ZZWRONG 3", ajax=False)
        self.assertRedirects(response, f"/p/{link.slug}/results/")
        self.assertEqual(ActivitySession.objects.get().score, 20)

    def test_card_order_is_stable_for_a_run(self):
        link = self.publish(question_bank(6, shuffle=True))
        self.start(link)

        first = [card["id"] for card in self.client.get(f"/p/{link.slug}/").context["runtime"]["cards"]]
        self.answer(link, first[0], f"ZZCORRECT {first[0].split('-')[1]}")
        second = self.client.get(f"/p/{link.slug}/").context["runtime"]["cards"]

        self.assertEqual([card["id"] for card in second], first)
        self.assertEqual([card["number"] for card in second], list(range(1, 7)))

    def test_unknown_choice_or_card_is_rejected(self):
        link = self.publish(question_bank(2))
        self.start(link)

        for item_key, answer in (("q-1", "made up"), ("q-1", ""), ("missing", "ZZCORRECT 1")):
            with self.subTest(item_key=item_key, answer=answer):
                response = self.answer(link, item_key, answer)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()["ok"])
        self.assertFalse(ActivityAnswer.objects.exists())

        response = self.answer(link, "q-1", "made up", ajax=False, follow=True)
        self.assertContains(response, "Такого варианта ответа нет")

    def test_first_saved_answer_is_final(self):
        link = self.publish(question_bank(2))
        self.start(link)
        self.answer(link, "q-1", "ZZWRONG 1")

        payload = self.answer(link, "q-1", "ZZCORRECT 1").json()

        self.assertTrue(payload["already_answered"])
        self.assertEqual(payload["feedback"]["submitted"], "ZZWRONG 1")
        self.assertEqual(ActivityAnswer.objects.count(), 1)

    def test_preview_checks_without_saving(self):
        for reveal, expected_correct in ((True, False), (False, None)):
            with self.subTest(reveal=reveal):
                link = self.publish(question_bank(2, reveal_correct_answer=reveal))
                self.client.force_login(self.teacher)

                response = self.client.post(
                    reverse("activities:preview_action", args=[link.activity.pk]),
                    {"action": "answer", "item_key": "q-1", "answer": "ZZWRONG 1"},
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["feedback"]["is_correct"], expected_correct)
                self.assertFalse(ActivitySession.objects.exists())
                self.client.logout()

    def test_legacy_whole_run_submission_still_finishes(self):
        link = self.publish(question_bank(2))
        self.start(link)
        self.answer(link, "q-1", "ZZWRONG 1")

        self.client.post(
            f"/p/{link.slug}/",
            {"action": "submit_categorize", "question_q-1": "ZZCORRECT 1", "question_q-2": "ZZCORRECT 2"},
        )

        session = ActivitySession.objects.get()
        self.assertEqual((session.status, session.score), (ActivitySession.Status.COMPLETED, 10))
