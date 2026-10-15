"""The per-answer protocol: answers are checked on the server and the page never carries the answer key."""
from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from activities.models import Activity, ShareLink
from attempts.models import ActivityAnswer, ActivitySession

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


def question_bank(count: int = 2, *, points: int = 10, **settings) -> dict:
    """Symmetric option texts: a leak check can count ZZCORRECT against ZZWRONG in the page."""
    return {
        **settings,
        "items": [
            {
                "id": f"q-{index}",
                "prompt": f"Question {index}?",
                "points": points,
                "options": [
                    {"id": f"q-{index}-option-1", "text": f"ZZCORRECT {index}", "is_correct": True},
                    {"id": f"q-{index}-option-2", "text": f"ZZWRONG {index}", "is_correct": False},
                ],
            }
            for index in range(1, count + 1)
        ],
    }


class AnswerProtocolTestCase(TestCase):
    template_key = "quiz"

    def setUp(self):
        self.teacher = User.objects.create_user(username=f"teacher-{self.template_key}", password="pass12345")

    def publish(self, config: dict, template_key: str | None = None) -> ShareLink:
        activity = Activity.objects.create(
            owner=self.teacher,
            title="Protocol",
            template_key=template_key or self.template_key,
            config_json=config,
            status=Activity.Status.PUBLISHED,
        )
        return ShareLink.objects.create(activity=activity)

    def start(self, link: ShareLink) -> ActivitySession:
        self.client.post(f"/p/{link.slug}/", {"action": "start"})
        return ActivitySession.objects.get(share_link=link)

    def answer(self, link: ShareLink, item_key: str, answer: str, *, ajax: bool = True, follow: bool = False, **extra):
        payload = {"action": "answer", "item_key": item_key, "answer": answer, **extra}
        return self.client.post(f"/p/{link.slug}/", payload, follow=follow, **(AJAX if ajax else {}))

    def assert_no_answer_key(self, response):
        html = response.content.decode()
        self.assertNotIn("data-correct", html)
        self.assertNotIn("expected_answer", html)
        self.assertNotIn("correct_option", html)
        self.assertEqual(html.count("ZZCORRECT"), html.count("ZZWRONG"))


class QuizAnswerProtocolTests(AnswerProtocolTestCase):
    def test_player_and_preview_html_carry_no_answer_key(self):
        for reveal in (True, False):
            with self.subTest(reveal=reveal):
                link = self.publish(question_bank(3, reveal_correct_answer=reveal))
                self.start(link)
                self.assert_no_answer_key(self.client.get(f"/p/{link.slug}/"))

                self.client.force_login(self.teacher)
                self.assert_no_answer_key(self.client.get(reverse("activities:preview", args=[link.activity.pk])))
                self.client.logout()

    def test_answer_json_shape_and_reveal_policy(self):
        for reveal, expected_correct in ((True, "ZZCORRECT 1"), (False, None)):
            with self.subTest(reveal=reveal):
                link = self.publish(question_bank(2, reveal_correct_answer=reveal))
                self.start(link)

                payload = self.answer(link, "q-1", "ZZWRONG 1").json()

                self.assertEqual(
                    payload["feedback"],
                    {"submitted": "ZZWRONG 1", "is_correct": False, "correct_option": expected_correct, "score_awarded": 0},
                )
                self.assertEqual((payload["answered_count"], payload["total_count"]), (1, 2))
                self.assertEqual((payload["score"], payload["max_score"]), (0, 20))
                self.assertFalse(payload["is_complete"])
                self.assertFalse(payload["already_answered"])

    def test_last_answer_completes_and_redirects(self):
        link = self.publish(question_bank(1))
        self.start(link)

        payload = self.answer(link, "q-1", "ZZCORRECT 1").json()

        self.assertTrue(payload["is_complete"])
        self.assertEqual(payload["redirect_url"], f"/p/{link.slug}/results/")
        session = ActivitySession.objects.get()
        self.assertEqual((session.status, session.score, float(session.percent_score)), ("completed", 10, 100.0))

    def test_first_saved_answer_is_final(self):
        link = self.publish(question_bank(2))
        self.start(link)
        self.answer(link, "q-1", "ZZWRONG 1")

        payload = self.answer(link, "q-1", "ZZCORRECT 1").json()

        self.assertTrue(payload["already_answered"])
        self.assertEqual(payload["feedback"]["submitted"], "ZZWRONG 1")
        self.assertEqual(ActivityAnswer.objects.count(), 1)
        self.assertEqual(ActivitySession.objects.get().score, 0)

    def test_existing_row_is_not_a_500(self):
        link = self.publish(question_bank(2))
        session = self.start(link)
        ActivityAnswer.objects.create(session=session, item_key="q-1", submitted_value={"choice": "ZZCORRECT 1"}, is_correct=True)

        response = self.answer(link, "q-1", "ZZWRONG 1")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["already_answered"])

    def test_progress_survives_a_reload_without_javascript(self):
        link = self.publish(question_bank(3))
        self.start(link)

        response = self.answer(link, "q-1", "ZZCORRECT 1", ajax=False)

        self.assertRedirects(response, f"/p/{link.slug}/")
        page = self.client.get(f"/p/{link.slug}/")
        self.assertEqual(page.context["runtime"]["current_item_id"], "q-2")
        self.assertEqual(page.context["runtime"]["answered_count"], 1)
        self.assertContains(page, "Верно. Ответ засчитан.")

    def test_invalid_answers_are_rejected(self):
        link = self.publish(question_bank(2))
        self.start(link)

        for item_key, answer in (("q-1", "made up"), ("q-1", ""), ("missing", "ZZCORRECT 1")):
            with self.subTest(item_key=item_key, answer=answer):
                response = self.answer(link, item_key, answer)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()["ok"])
        self.assertFalse(ActivityAnswer.objects.exists())

    def test_error_without_javascript_is_a_message_on_the_play_page(self):
        link = self.publish(question_bank(2))
        self.start(link)

        response = self.answer(link, "q-1", "made up", ajax=False, follow=True)

        self.assertContains(response, "Такого варианта ответа нет")

    def test_score_follows_the_current_points_and_questions(self):
        link = self.publish(question_bank(3))
        self.start(link)
        self.answer(link, "q-1", "ZZCORRECT 1")
        activity = link.activity
        activity.config_json["items"][0]["points"] = 50
        activity.config_json["items"] = activity.config_json["items"][:1] + activity.config_json["items"][2:]
        activity.save()

        payload = self.answer(link, "q-3", "ZZCORRECT 3").json()

        self.assertEqual((payload["score"], payload["max_score"]), (60, 60))
        self.assertTrue(payload["is_complete"])

    def test_answer_without_a_started_run_is_409(self):
        link = self.publish(question_bank(1))

        response = self.answer(link, "q-1", "ZZCORRECT 1")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["redirect_url"], f"/p/{link.slug}/")

    def test_answering_a_finished_run_points_to_results(self):
        link = self.publish(question_bank(2))
        self.start(link)
        self.answer(link, "q-1", "ZZCORRECT 1")
        ActivitySession.objects.update(status=ActivitySession.Status.COMPLETED)

        response = self.answer(link, "q-2", "ZZCORRECT 2")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["redirect_url"], f"/p/{link.slug}/results/")

    def test_actions_of_pages_before_per_answer_checks_are_rejected(self):
        old_actions = {
            "quiz": {"action": "submit_quiz", "question_q-1": "ZZCORRECT 1", "question_q-2": "ZZCORRECT 2"},
            "matching": {"action": "submit_matching", "match_q-1": "ZZCORRECT 1", "match_q-2": "ZZCORRECT 2"},
            "categorize": {"action": "submit_categorize", "question_q-1": "ZZCORRECT 1", "question_q-2": "ZZCORRECT 2"},
            "snake": {"action": "submit_snake", "question_q-1": "ZZCORRECT 1", "question_q-2": "ZZCORRECT 2"},
            "choose_a_box": {"action": "answer_box", "item_key": "q-1", "answer": "ZZCORRECT 1"},
            "wheel_of_fortune": {"action": "answer_wheel", "item_key": "q-1", "answer": "ZZCORRECT 1"},
        }
        for template_key, payload in old_actions.items():
            with self.subTest(template_key=template_key):
                link = self.publish(question_bank(2), template_key=template_key)
                session = self.start(link)

                response = self.client.post(f"/p/{link.slug}/", payload, **AJAX)

                self.assertEqual(response.status_code, 400)
                self.assertIn("Обновите страницу", response.json()["error"])
                session.refresh_from_db()
                self.assertEqual(session.status, ActivitySession.Status.STARTED)
                self.assertFalse(session.answers.exists())


class PreviewActionTests(AnswerProtocolTestCase):
    def setUp(self):
        super().setUp()
        self.link = self.publish(question_bank(2))
        self.url = reverse("activities:preview_action", args=[self.link.activity.pk])

    def test_owner_gets_feedback_and_nothing_is_saved(self):
        self.client.force_login(self.teacher)

        response = self.client.post(self.url, {"action": "answer", "item_key": "q-1", "answer": "ZZWRONG 1"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["feedback"]["is_correct"], False)
        self.assertFalse(ActivitySession.objects.exists())
        self.assertFalse(ActivityAnswer.objects.exists())

    def test_other_teacher_and_guests_are_kept_out(self):
        other = User.objects.create_user(username="other-teacher", password="pass12345")
        self.client.force_login(other)
        self.assertEqual(self.client.post(self.url, {"action": "answer"}).status_code, 404)

        self.client.logout()
        self.assertEqual(self.client.post(self.url, {"action": "answer"}).status_code, 302)

    def test_get_is_not_allowed(self):
        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(self.url).status_code, 405)


class MidRunChangesTests(AnswerProtocolTestCase):
    def test_run_completes_when_the_remaining_questions_were_deleted(self):
        link = self.publish(question_bank(3))
        self.start(link)
        self.answer(link, "q-1", "ZZCORRECT 1")
        self.answer(link, "q-2", "ZZWRONG 2")
        activity = link.activity
        activity.config_json["items"] = activity.config_json["items"][:2]
        activity.save()

        response = self.client.get(f"/p/{link.slug}/")

        self.assertRedirects(response, f"/p/{link.slug}/results/")
        session = ActivitySession.objects.get()
        self.assertEqual((session.status, session.score, session.max_score), ("completed", 10, 20))

    def test_second_tab_after_completion_goes_to_results(self):
        link = self.publish(question_bank(1))
        self.start(link)
        self.answer(link, "q-1", "ZZCORRECT 1")

        response = self.answer(link, "q-1", "ZZWRONG 1")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["redirect_url"], f"/p/{link.slug}/results/")
        self.assertRedirects(self.answer(link, "q-1", "ZZWRONG 1", ajax=False), f"/p/{link.slug}/results/")

    def test_imported_config_with_integer_ids_and_padded_options(self):
        config = question_bank(1)
        config["items"][0]["id"] = 7
        config["items"][0]["options"][0]["text"] = " ZZCORRECT 1 "
        link = self.publish(config)
        self.start(link)

        payload = self.answer(link, "7", "ZZCORRECT 1").json()

        self.assertTrue(payload["feedback"]["is_correct"])
        self.assertTrue(payload["is_complete"])
