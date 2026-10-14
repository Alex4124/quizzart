"""Matching on the per-answer protocol: one shared bank of cards, every row is checked on the server."""
from __future__ import annotations

from django.urls import reverse

from attempts.models import ActivityAnswer, ActivitySession
from attempts.test_answers import AJAX, AnswerProtocolTestCase, question_bank


def reused_bank() -> dict:
    """Two rows share one card (in another letter case), a third row has its own."""
    return {
        "shuffle": False,
        "items": [
            {
                "id": "q-1",
                "prompt": "First statement",
                "points": 10,
                "options": [
                    {"id": "q-1-a", "text": "Верно", "is_correct": True},
                    {"id": "q-1-b", "text": "Неверно", "is_correct": False},
                ],
            },
            {
                "id": "q-2",
                "prompt": "Second statement",
                "points": 10,
                "options": [
                    {"id": "q-2-a", "text": "ВЕРНО", "is_correct": True},
                    {"id": "q-2-b", "text": "Неверно", "is_correct": False},
                ],
            },
            {
                "id": "q-3",
                "prompt": "Third statement",
                "points": 10,
                "options": [
                    {"id": "q-3-a", "text": "Не знаю", "is_correct": True},
                    {"id": "q-3-b", "text": "верно", "is_correct": False},
                ],
            },
        ],
    }


class MatchingAnswerProtocolTests(AnswerProtocolTestCase):
    template_key = "matching"

    def assert_no_answer_key(self, response, *, symmetric: bool = True):
        html = response.content.decode()
        if symmetric:
            super().assert_no_answer_key(response)
        for marker in ("data-correct", "expected_answer", "correct_option", "correct_choice", "is_correct", "review_items"):
            self.assertNotIn(marker, html)
        # Card ids follow the authoring order, where teachers usually put the right answer first.
        self.assertNotRegex(html, r"matching-choice-\d")
        runtime = response.context["runtime"]
        self.assertNotIn("review_items", runtime)
        for row in runtime["rows"]:
            self.assertFalse(row["is_answered"])
            self.assertEqual(
                set(row),
                {"id", "number", "prompt", "points", "is_answered", "feedback", "placed_card", "right_card"},
            )

    def assert_page_and_preview_carry_no_answer_key(self, config: dict, *, symmetric: bool = True):
        link = self.publish(config)
        self.start(link)
        self.assert_no_answer_key(self.client.get(f"/p/{link.slug}/"), symmetric=symmetric)

        self.client.force_login(self.teacher)
        self.assert_no_answer_key(
            self.client.get(reverse("activities:preview", args=[link.activity.pk])),
            symmetric=symmetric,
        )
        self.client.logout()

    def test_player_and_preview_html_carry_no_answer_key(self):
        # Matching has no reveal setting; a stray one from another template changes nothing.
        for settings in ({"shuffle": True}, {"shuffle": False}, {"shuffle": True, "reveal_correct_answer": False}):
            with self.subTest(**settings):
                self.assert_page_and_preview_carry_no_answer_key(question_bank(3, **settings))

    def test_correct_answers_only_bank_carries_no_answer_key(self):
        # Every card is somebody's right answer here, so ZZCORRECT and ZZWRONG cannot be counted against each other.
        self.assert_page_and_preview_carry_no_answer_key(
            question_bank(3, shuffle=True, correct_answers_only=True),
            symmetric=False,
        )

    def test_bank_cards_submit_the_first_unanswered_row(self):
        link = self.publish(question_bank(2, shuffle=False))
        self.start(link)

        page = self.client.get(f"/p/{link.slug}/")

        self.assertEqual(page.context["runtime"]["current_item_id"], "q-1")
        self.assertContains(page, 'id="matching-answer-q-1"', count=1)
        self.assertContains(page, 'form="matching-answer-q-1"', count=4)
        self.assertContains(page, 'type="submit"', count=4)
        self.assertContains(page, '<input type="hidden" name="item_key" value="q-1">', html=True)
        self.assertContains(page, 'aria-live="polite"', count=2)
        # No whole-run form and no finish button: the run completes with the last row.
        self.assertNotContains(page, "submit_matching")
        self.assertNotContains(page, 'name="match_')
        self.assertNotContains(page, "Завершить сопоставление")

    def test_bank_order_is_shuffled_per_run_and_stable_on_reload(self):
        config = question_bank(6, shuffle=True)
        link = self.publish(config)
        self.start(link)

        first = [card["text"] for card in self.client.get(f"/p/{link.slug}/").context["runtime"]["answer_bank"]]
        again = [card["text"] for card in self.client.get(f"/p/{link.slug}/").context["runtime"]["answer_bank"]]

        self.assertEqual(first, again)
        self.assertCountEqual(first, [option["text"] for item in config["items"] for option in item["options"]])
        self.assertNotEqual(first, [option["text"] for item in config["items"] for option in item["options"]])

    def test_wrong_card_gets_the_right_card_back(self):
        link = self.publish(question_bank(2, shuffle=False))
        self.start(link)

        payload = self.answer(link, "q-1", "ZZWRONG 1").json()

        self.assertEqual(
            payload["feedback"],
            {
                "submitted": "ZZWRONG 1",
                "is_correct": False,
                "correct_option": "ZZCORRECT 1",
                "correct_choice_id": "matching-choice-1",
                "score_awarded": 0,
            },
        )
        self.assertEqual((payload["answered_count"], payload["total_count"]), (1, 2))
        self.assertEqual((payload["score"], payload["max_score"]), (0, 20))
        self.assertFalse(payload["is_complete"])
        self.assertIsNone(payload["redirect_url"])

    def test_a_card_reused_by_several_rows_scores_in_any_letter_case(self):
        link = self.publish(reused_bank())
        self.start(link)
        page = self.client.get(f"/p/{link.slug}/")
        self.assertEqual(
            [card["text"] for card in page.context["runtime"]["answer_bank"]],
            ["Верно", "Неверно", "Не знаю"],
        )

        first = self.answer(link, "q-1", "Верно").json()
        second = self.answer(link, "q-2", "Верно").json()
        third = self.answer(link, "q-3", "верно").json()

        self.assertEqual((first["feedback"]["is_correct"], second["feedback"]["is_correct"]), (True, True))
        self.assertEqual(second["feedback"]["correct_option"], "Верно")
        self.assertEqual(second["feedback"]["correct_choice_id"], "matching-choice-1")
        self.assertEqual(
            {key: third["feedback"][key] for key in ("submitted", "is_correct", "correct_option", "correct_choice_id")},
            {"submitted": "Верно", "is_correct": False, "correct_option": "Не знаю", "correct_choice_id": "matching-choice-3"},
        )
        self.assertTrue(third["is_complete"])
        self.assertEqual(third["redirect_url"], f"/p/{link.slug}/results/")
        session = ActivitySession.objects.get()
        self.assertEqual((session.status, session.score, session.max_score), ("completed", 20, 30))

    def test_progress_survives_a_reload_without_javascript(self):
        link = self.publish(question_bank(3, shuffle=False))
        self.start(link)

        response = self.answer(link, "q-1", "ZZWRONG 1", ajax=False)

        self.assertRedirects(response, f"/p/{link.slug}/")
        page = self.client.get(f"/p/{link.slug}/")
        runtime = page.context["runtime"]
        self.assertEqual(runtime["current_item_id"], "q-2")
        self.assertEqual((runtime["answered_count"], runtime["total_count"]), (1, 3))
        answered = runtime["rows"][0]
        self.assertEqual(answered["placed_card"], {"text": "ZZWRONG 1", "number": 2})
        self.assertEqual(answered["right_card"], {"text": "ZZCORRECT 1", "number": 1})
        self.assertContains(page, "Неверно. Правильный ответ: ZZCORRECT 1")
        self.assertContains(page, 'data-state="answered"', count=1)
        self.assertContains(page, 'form="matching-answer-q-2"', count=6)
        self.assertContains(page, "1 из 3")

        self.answer(link, "q-2", "ZZCORRECT 2", ajax=False)
        last = self.answer(link, "q-3", "ZZCORRECT 3", ajax=False)

        self.assertRedirects(last, f"/p/{link.slug}/results/")
        session = ActivitySession.objects.get()
        self.assertEqual((session.status, session.score), ("completed", 20))

    def test_a_right_card_after_a_reload_has_no_second_card(self):
        link = self.publish(question_bank(2, shuffle=False))
        self.start(link)
        self.answer(link, "q-1", "ZZCORRECT 1", ajax=False)

        row = self.client.get(f"/p/{link.slug}/").context["runtime"]["rows"][0]

        self.assertEqual(row["placed_card"], {"text": "ZZCORRECT 1", "number": 1})
        self.assertIsNone(row["right_card"])

    def test_wrong_and_unknown_choices_are_rejected(self):
        link = self.publish(question_bank(2, shuffle=False, correct_answers_only=True))
        self.start(link)

        for item_key, answer in (
            ("q-1", "made up"),
            ("q-1", ""),
            # Not in the bank: correct_answers_only keeps only the right answers.
            ("q-1", "ZZWRONG 1"),
            ("missing", "ZZCORRECT 1"),
        ):
            with self.subTest(item_key=item_key, answer=answer):
                response = self.answer(link, item_key, answer)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()["ok"])
        self.assertFalse(ActivityAnswer.objects.exists())

    def test_first_saved_answer_is_final(self):
        link = self.publish(question_bank(2, shuffle=False))
        self.start(link)
        self.answer(link, "q-1", "ZZWRONG 1")

        payload = self.answer(link, "q-1", "ZZCORRECT 1").json()

        self.assertTrue(payload["already_answered"])
        self.assertEqual(payload["feedback"]["submitted"], "ZZWRONG 1")
        self.assertEqual(ActivitySession.objects.get().score, 0)

    def test_preview_checks_without_saving(self):
        link = self.publish(question_bank(2, shuffle=False))
        self.client.force_login(self.teacher)
        url = reverse("activities:preview_action", args=[link.activity.pk])

        page = self.client.get(reverse("activities:preview", args=[link.activity.pk]))
        response = self.client.post(url, {"action": "answer", "item_key": "q-1", "answer": "ZZWRONG 1"}, **AJAX)

        self.assertContains(page, f'data-action-url="{url}"')
        self.assertContains(page, "data-preview-complete")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["feedback"]["correct_choice_id"], "matching-choice-1")
        self.assertFalse(ActivitySession.objects.exists())
        self.assertFalse(ActivityAnswer.objects.exists())

    def test_legacy_whole_run_submit_still_completes(self):
        link = self.publish(question_bank(2, shuffle=False))
        self.start(link)
        self.answer(link, "q-1", "ZZWRONG 1")

        self.client.post(f"/p/{link.slug}/", {"action": "submit_matching", "match_q-1": "ZZCORRECT 1", "match_q-2": "zzcorrect 2"})

        session = ActivitySession.objects.get()
        self.assertEqual((session.status, session.score), ("completed", 10))
        self.assertFalse(session.answers.get(item_key="q-1").is_correct)

    def test_results_still_list_every_pair(self):
        link = self.publish(question_bank(2, shuffle=False))
        self.start(link)
        self.answer(link, "q-1", "ZZWRONG 1")
        self.answer(link, "q-2", "ZZCORRECT 2")

        results = self.client.get(f"/p/{link.slug}/results/")

        self.assertEqual(len(results.context["runtime"]["review_items"]), 2)
        self.assertContains(results, "Question 1?")
        self.assertContains(results, "Question 2?")
