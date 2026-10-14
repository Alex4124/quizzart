"""The wheel on the per-answer protocol: the server picks the sector, the page never carries the answer key."""
from __future__ import annotations

import re
from unittest import mock

from django.urls import reverse

from attempts.models import ActivityAnswer, ActivitySession
from attempts.test_answers import AJAX, AnswerProtocolTestCase, question_bank

RNG_CHOICE = "interactive_templates.definitions.wheel_of_fortune._rng.choice"


def lands_on(item_key: str):
    """Patches the server's sector pick; the mock keeps the sectors it was offered."""
    return mock.patch(RNG_CHOICE, side_effect=lambda candidates: item_key)


class WheelAnswerProtocolTests(AnswerProtocolTestCase):
    template_key = "wheel_of_fortune"

    def spin(self, link, *, ajax: bool = True, follow: bool = False):
        return self.client.post(f"/p/{link.slug}/", {"action": "spin"}, follow=follow, **(AJAX if ajax else {}))

    def spin_to(self, link, item_key: str) -> dict:
        with lands_on(item_key):
            return self.spin(link).json()

    def play_page(self, link):
        return self.client.get(f"/p/{link.slug}/")

    def visible_cards(self, html: str) -> list[str]:
        cards = re.findall(r"<article[^>]*data-wheel-question[^>]*>", html)
        return [re.search(r'data-item-id="([^"]+)"', card).group(1) for card in cards if " hidden" not in card]

    def test_player_and_preview_html_carry_no_answer_key(self):
        for reveal in (True, False):
            with self.subTest(reveal=reveal):
                link = self.publish(question_bank(3, reveal_correct_answer=reveal))
                self.start(link)

                page = self.play_page(link)
                self.assert_no_answer_key(page)
                self.assertNotIn("review_items", page.context["runtime"])

                self.spin_to(link, "q-2")
                page = self.play_page(link)
                self.assert_no_answer_key(page)
                runtime = page.context["runtime"]
                self.assertNotIn("correct_option", runtime["active_item"])
                self.assertTrue(all("correct_option" not in sector for sector in runtime["sectors"]))

                self.client.force_login(self.teacher)
                self.assert_no_answer_key(self.client.get(reverse("activities:preview", args=[link.activity.pk])))
                self.client.logout()

    def test_answer_without_a_spin_is_rejected(self):
        link = self.publish(question_bank(2))
        self.start(link)

        response = self.answer(link, "q-1", "ZZCORRECT 1")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Сначала раскрутите колесо.")
        self.assertFalse(ActivityAnswer.objects.exists())

    def test_answer_to_another_sector_is_rejected(self):
        link = self.publish(question_bank(3))
        self.start(link)
        self.spin_to(link, "q-1")

        response = self.answer(link, "q-2", "ZZCORRECT 2")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "Ответьте на вопрос сектора, на котором остановилось колесо.")
        self.assertFalse(ActivityAnswer.objects.exists())
        payload = self.answer(link, "q-1", "ZZCORRECT 1").json()
        self.assertEqual(payload["feedback"]["is_correct"], True)

    def test_spinning_again_returns_the_open_question(self):
        link = self.publish(question_bank(3))
        self.start(link)
        first = self.spin_to(link, "q-2")["spin"]

        with lands_on("q-3") as choice:
            second = self.spin(link).json()["spin"]

        self.assertEqual(first, {"item_key": "q-2", "repeat": False, "resumed": False})
        self.assertEqual(second, {"item_key": "q-2", "repeat": False, "resumed": True})
        choice.assert_not_called()

    def test_no_repeat_spins_only_unanswered_sectors(self):
        link = self.publish(question_bank(3, no_repeat=True))
        self.start(link)
        self.spin_to(link, "q-1")
        self.answer(link, "q-1", "ZZWRONG 1")

        with lands_on("q-3") as choice:
            spin = self.spin(link).json()["spin"]

        choice.assert_called_once_with(["q-2", "q-3"])
        self.assertEqual(spin, {"item_key": "q-3", "repeat": False, "resumed": False})

    def test_repeats_allowed_landing_on_an_answered_sector_shows_the_saved_answer(self):
        link = self.publish(question_bank(3, no_repeat=False))
        session = self.start(link)
        self.spin_to(link, "q-1")
        self.answer(link, "q-1", "ZZWRONG 1")

        with lands_on("q-1") as choice:
            payload = self.spin(link).json()

        choice.assert_called_once_with(["q-1", "q-2", "q-3"])
        self.assertEqual(
            payload["spin"],
            {
                "item_key": "q-1",
                "repeat": True,
                "resumed": False,
                "previous": {"submitted": "ZZWRONG 1", "is_correct": False, "correct_option": "ZZCORRECT 1", "score_awarded": 0},
            },
        )
        self.assertFalse(payload["is_complete"])
        session.refresh_from_db()
        self.assertEqual(session.runtime_state["active_item"], "")
        # No question is open, so the wheel can be spun again and the next sector answered.
        self.assertEqual(self.answer(link, "q-1", "ZZCORRECT 1").json()["already_answered"], True)
        self.assertEqual(self.spin_to(link, "q-2")["spin"], {"item_key": "q-2", "repeat": False, "resumed": False})
        self.assertEqual(self.answer(link, "q-2", "ZZCORRECT 2").json()["feedback"]["is_correct"], True)
        self.assertEqual(self.play_page(link).context["runtime"]["active_item"], None)

    def test_spin_json_never_carries_the_correct_option(self):
        for reveal in (True, False):
            with self.subTest(reveal=reveal):
                link = self.publish(question_bank(2, no_repeat=False, reveal_correct_answer=reveal))
                self.start(link)

                with lands_on("q-1"):
                    response = self.spin(link)
                self.assertNotIn("ZZCORRECT", response.content.decode())
                self.assertNotIn("correct_option", response.json()["spin"])

                self.answer(link, "q-1", "ZZWRONG 1")
                with lands_on("q-1"):
                    repeat = self.spin(link).json()["spin"]
                self.assertEqual(repeat["previous"]["correct_option"], "ZZCORRECT 1" if reveal else None)

    def test_a_reload_shows_the_open_question_and_marks_answered_sectors(self):
        link = self.publish(question_bank(3))
        self.start(link)
        self.spin_to(link, "q-1")
        self.answer(link, "q-1", "ZZCORRECT 1")
        self.spin_to(link, "q-3")

        page = self.play_page(link)

        html = page.content.decode()
        runtime = page.context["runtime"]
        self.assertEqual(runtime["active_item"]["id"], "q-3")
        self.assertEqual((runtime["answered_count"], runtime["total_count"]), (1, 3))
        self.assertIn('data-active-item="q-3"', html)
        self.assertEqual(self.visible_cards(html), ["q-3"])
        self.assertEqual([sector["id"] for sector in runtime["sectors"] if sector["is_answered"]], ["q-1"])
        self.assertRegex(html, r'data-item-id="q-1"\s+data-answered="1"')
        self.assertEqual(page.context["player_shell"]["answered_count"], 1)
        self.assertRegex(html, r"data-wheel-start disabled")

    def test_without_javascript_the_spin_form_opens_the_question(self):
        link = self.publish(question_bank(2))
        self.start(link)
        page = self.play_page(link)
        self.assertContains(page, '<input type="hidden" name="action" value="spin">', html=False)
        self.assertEqual(self.visible_cards(page.content.decode()), [])

        with lands_on("q-2"):
            response = self.spin(link, ajax=False)

        self.assertRedirects(response, f"/p/{link.slug}/")
        page = self.play_page(link)
        self.assertEqual(self.visible_cards(page.content.decode()), ["q-2"])
        response = self.answer(link, "q-2", "ZZCORRECT 2", ajax=False)
        self.assertRedirects(response, f"/p/{link.slug}/")
        page = self.play_page(link)
        self.assertEqual(self.visible_cards(page.content.decode()), [])
        self.assertEqual(page.context["runtime"]["answered_count"], 1)

    def test_answer_without_a_spin_without_javascript_is_a_message(self):
        link = self.publish(question_bank(2))
        self.start(link)

        response = self.answer(link, "q-1", "ZZCORRECT 1", ajax=False, follow=True)

        self.assertContains(response, "Сначала раскрутите колесо.")

    def test_answer_posted_again_keeps_the_saved_answer_and_the_open_question(self):
        link = self.publish(question_bank(3))
        session = self.start(link)
        self.spin_to(link, "q-1")
        self.answer(link, "q-1", "ZZWRONG 1")
        self.spin_to(link, "q-2")

        payload = self.answer(link, "q-1", "ZZCORRECT 1").json()

        self.assertTrue(payload["already_answered"])
        self.assertEqual(payload["feedback"]["submitted"], "ZZWRONG 1")
        session.refresh_from_db()
        self.assertEqual(session.runtime_state["active_item"], "q-2")
        self.assertEqual(session.score, 0)

    def test_early_finish_after_one_answer(self):
        link = self.publish(question_bank(3))
        self.start(link)
        self.assertRegex(self.play_page(link).content.decode(), r"data-wheel-finish hidden")
        self.spin_to(link, "q-2")
        self.answer(link, "q-2", "ZZCORRECT 2")
        page = self.play_page(link)
        self.assertRegex(page.content.decode(), r"data-wheel-finish>")
        self.assertContains(page, 'name="action" value="finish"', html=False)

        response = self.client.post(f"/p/{link.slug}/", {"action": "finish"})

        self.assertRedirects(response, f"/p/{link.slug}/results/")
        session = ActivitySession.objects.get()
        self.assertEqual((session.status, session.score, session.max_score), ("completed", 10, 30))

    def test_spin_with_every_sector_answered_completes_the_run(self):
        link = self.publish(question_bank(2))
        session = self.start(link)
        for key in ("q-1", "q-2"):
            ActivityAnswer.objects.create(session=session, item_key=key, submitted_value={"choice": "x"}, is_correct=False)

        payload = self.spin(link).json()

        self.assertIsNone(payload["spin"])
        self.assertTrue(payload["is_complete"])
        self.assertEqual(payload["redirect_url"], f"/p/{link.slug}/results/")

    def test_legacy_spin_and_answer_actions_still_work(self):
        link = self.publish(question_bank(1))
        self.start(link)

        self.client.post(f"/p/{link.slug}/", {"action": "spin_wheel"})
        response = self.client.post(f"/p/{link.slug}/", {"action": "answer_wheel", "answer": "ZZCORRECT 1"})

        self.assertRedirects(response, f"/p/{link.slug}/results/")
        self.assertEqual(ActivitySession.objects.get().score, 10)


class WheelPreviewTests(AnswerProtocolTestCase):
    template_key = "wheel_of_fortune"

    def preview_action(self, link, data: dict):
        return self.client.post(reverse("activities:preview_action", args=[link.activity.pk]), data)

    def test_preview_page_has_no_finish_and_a_completion_note(self):
        link = self.publish(question_bank(2))
        self.client.force_login(self.teacher)

        page = self.client.get(reverse("activities:preview", args=[link.activity.pk]))

        self.assertNotContains(page, "data-wheel-finish")
        self.assertContains(page, "data-preview-complete")
        self.assertContains(page, 'data-preview="1"')

    def test_preview_spin_respects_answered_and_the_open_question(self):
        link = self.publish(question_bank(3))
        self.client.force_login(self.teacher)

        with lands_on("q-3") as choice:
            spin = self.preview_action(link, {"action": "spin", "answered": ["q-1", "q-2"], "active_item": ""}).json()["spin"]
        choice.assert_called_once_with(["q-3"])
        self.assertEqual(spin, {"item_key": "q-3", "repeat": False, "resumed": False})

        resumed = self.preview_action(link, {"action": "spin", "answered": ["q-1"], "active_item": "q-2"}).json()["spin"]
        self.assertEqual(resumed, {"item_key": "q-2", "repeat": False, "resumed": True})

        done = self.preview_action(link, {"action": "spin", "answered": ["q-1", "q-2", "q-3"]}).json()
        self.assertIsNone(done["spin"])
        self.assertFalse(ActivitySession.objects.exists())

    def test_preview_with_repeats_allowed_can_land_on_an_answered_sector(self):
        link = self.publish(question_bank(2, no_repeat=False))
        self.client.force_login(self.teacher)

        with lands_on("q-1") as choice:
            spin = self.preview_action(link, {"action": "spin", "answered": ["q-1"]}).json()["spin"]

        choice.assert_called_once_with(["q-1", "q-2"])
        self.assertEqual(spin, {"item_key": "q-1", "repeat": True, "resumed": False})

    def test_preview_answer_gives_feedback_and_saves_nothing(self):
        link = self.publish(question_bank(2, reveal_correct_answer=False))
        self.client.force_login(self.teacher)

        response = self.preview_action(link, {"action": "answer", "item_key": "q-2", "answer": "ZZWRONG 2"})

        self.assertEqual(
            response.json()["feedback"],
            {"submitted": "ZZWRONG 2", "is_correct": False, "correct_option": None, "score_awarded": 0},
        )
        self.assertFalse(ActivityAnswer.objects.exists())
