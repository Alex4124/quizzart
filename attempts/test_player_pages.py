"""The student's start and results pages: what they show, and that results follow the reveal policy."""
from __future__ import annotations

import re
from unittest import mock

from django.urls import reverse

from attempts.test_answers import AJAX, AnswerProtocolTestCase, question_bank

RNG_CHOICE = "interactive_templates.definitions.wheel_of_fortune._rng.choice"

# Template -> what an item is called in the review.
REVIEW_LABELS = {
    "quiz": "Вопрос",
    "choose_a_box": "Коробка",
    "wheel_of_fortune": "Сектор",
    "matching": "Пара",
    "categorize": "Карточка",
    "snake": "Яблоко",
}


def body_html(response) -> str:
    """The page without its <head>: the <title> repeats the activity title on purpose."""
    return response.content.decode().split("<body", 1)[1]


class PlayerPagesTestCase(AnswerProtocolTestCase):
    def answer_item(self, link, item_key: str, answer: str):
        template_key = link.activity.template_key
        if template_key == "wheel_of_fortune":
            with mock.patch(RNG_CHOICE, side_effect=lambda candidates: item_key):
                self.client.post(f"/p/{link.slug}/", {"action": "spin"}, **AJAX)
        return self.answer(link, item_key, answer)

    def run_to_results(self, link, answers: dict[str, str]):
        self.start(link)
        for item_key, answer in answers.items():
            self.answer_item(link, item_key, answer)
        response = self.client.get(f"/p/{link.slug}/results/")
        self.assertEqual(response.status_code, 200)
        return response


class LaunchPageTests(PlayerPagesTestCase):
    def test_title_and_description_appear_once_and_no_zero_stats(self):
        for template_key in REVIEW_LABELS:
            with self.subTest(template_key=template_key):
                link = self.publish(question_bank(3), template_key=template_key)
                link.activity.title = "Неповторимое название"
                link.activity.description = "Единственное описание интерактива"
                link.activity.save()

                response = self.client.get(f"/p/{link.slug}/")
                html = body_html(response)

                self.assertEqual(html.count("Неповторимое название"), 1)
                self.assertEqual(html.count("Единственное описание интерактива"), 1)
                # Nothing is answered yet: no score, no progress ring, no «0 из 3».
                self.assertNotIn("data-player-summary-card", html)
                self.assertNotIn("data-player-progress-ring", html)
                self.assertNotIn("готово", html)
                self.assertNotIn("0 из 3", html)
                self.assertNotIn("Очки", html)
                self.assertContains(response, 'name="participant_name"')
                self.assertContains(response, "Начать интерактив")

    def test_launch_facts_tell_the_size_points_and_the_end(self):
        link = self.publish(question_bank(3, points=20))
        facts = {fact["key"]: fact["text"] for fact in self.client.get(f"/p/{link.slug}/").context["player_shell"]["launch_facts"]}
        self.assertEqual(facts, {"count": "3 вопроса", "points": "Максимум 60 баллов", "end": "В конце — разбор ответов"})

        scoreless = self.publish(question_bank(5, scoring_enabled=False), template_key="snake")
        response = self.client.get(f"/p/{scoreless.slug}/")
        self.assertContains(response, "5 яблок")
        self.assertContains(response, "Без баллов: считаются верные ответы")
        self.assertNotContains(response, "Максимум")

        total_only = self.publish(question_bank(1, show_result_at_end=False))
        response = self.client.get(f"/p/{total_only.slug}/")
        self.assertContains(response, "1 вопрос<")
        self.assertContains(response, "В конце — только итог")

    def test_name_stays_optional(self):
        link = self.publish(question_bank(1))
        response = self.client.post(f"/p/{link.slug}/", {"action": "start", "participant_name": ""})
        self.assertRedirects(response, f"/p/{link.slug}/")
        self.assertContains(self.client.get(f"/p/{link.slug}/"), "data-quiz-question")


class ResultsSummaryTests(PlayerPagesTestCase):
    def test_one_summary_labelled_as_the_result(self):
        link = self.publish(question_bank(2))
        response = self.run_to_results(link, {"q-1": "ZZCORRECT 1", "q-2": "ZZWRONG 2"})
        html = body_html(response)

        cards = {card["key"]: card for card in response.context["player_shell"]["summary_cards"]}
        self.assertEqual(list(cards), ["result", "score", "answered"])
        self.assertEqual((cards["result"]["label"], cards["result"]["value"]), ("Результат", "50%"))
        self.assertEqual((cards["score"]["label"], cards["score"]["value"], cards["score"]["suffix"]), ("Баллы", "10", "из 20"))
        self.assertEqual((cards["answered"]["value"], cards["answered"]["suffix"]), ("2", "из 2"))
        # The ring shows the result, not a completion of 50%.
        self.assertIn("Результат 50%", html)
        self.assertNotIn("готово", html)
        # The score is not repeated under other names.
        for label in ("Очки", "Максимум", "Процент"):
            self.assertNotIn(label, html)

    def test_points_per_item_are_what_the_answer_earned(self):
        link = self.publish(question_bank(2, points=10))
        response = self.run_to_results(link, {"q-1": "ZZCORRECT 1", "q-2": "ZZWRONG 2"})
        self.assertContains(response, ">10 из 10 баллов<", count=1)
        self.assertContains(response, ">0 из 10 баллов<", count=1)

    def test_scoreless_summary_counts_right_answers(self):
        link = self.publish(question_bank(3, scoring_enabled=False), template_key="categorize")
        response = self.run_to_results(link, {"q-1": "ZZCORRECT 1", "q-2": "ZZWRONG 2", "q-3": "ZZCORRECT 3"})
        score_card = next(card for card in response.context["player_shell"]["summary_cards"] if card["key"] == "score")
        self.assertEqual((score_card["label"], score_card["value"], score_card["suffix"]), ("Верно", "2", "из 3"))
        self.assertNotContains(response, "балл")


class ResultsRevealPolicyTests(PlayerPagesTestCase):
    def test_correct_answer_shown_only_when_the_activity_reveals_it(self):
        for template_key in ("quiz", "choose_a_box", "wheel_of_fortune", "categorize", "snake"):
            for reveal in (True, False):
                with self.subTest(template_key=template_key, reveal=reveal):
                    link = self.publish(question_bank(2, reveal_correct_answer=reveal), template_key=template_key)
                    response = self.run_to_results(link, {"q-1": "ZZWRONG 1", "q-2": "ZZWRONG 2"})
                    items = response.context["runtime"]["review_items"]

                    # The student's own answers and the verdict stay in both cases.
                    self.assertContains(response, "Ваш ответ: ZZWRONG 1")
                    self.assertContains(response, "Ваш ответ: ZZWRONG 2")
                    self.assertEqual([item["status"] for item in items], ["wrong", "wrong"])
                    self.assertContains(response, ">Неверно</span>", count=2)
                    if reveal:
                        self.assertContains(response, "Правильный ответ: ZZCORRECT 1")
                        self.assertContains(response, "Правильный ответ: ZZCORRECT 2")
                    else:
                        self.assertEqual([item["correct"] for item in items], [None, None])
                        self.assertNotContains(response, "ZZCORRECT")
                        self.assertNotContains(response, "Правильный ответ:")

    def test_matching_has_no_setting_and_always_shows_the_right_card(self):
        link = self.publish(question_bank(2, reveal_correct_answer=False), template_key="matching")
        response = self.run_to_results(link, {"q-1": "ZZWRONG 1", "q-2": "ZZCORRECT 2"})
        self.assertContains(response, "Правильный ответ: ZZCORRECT 1")
        # A right answer is not repeated as «Правильный ответ».
        self.assertContains(response, "Правильный ответ:", count=1)
        self.assertContains(response, ">Верно</span>", count=1)
        self.assertContains(response, ">Неверно</span>", count=1)

    def test_skipped_items_are_without_answer_and_keep_their_key(self):
        for template_key in ("choose_a_box", "wheel_of_fortune"):
            with self.subTest(template_key=template_key):
                link = self.publish(question_bank(3, reveal_correct_answer=True), template_key=template_key)
                self.start(link)
                self.answer_item(link, "q-1", "ZZWRONG 1")
                self.client.post(f"/p/{link.slug}/", {"action": "finish"})

                response = self.client.get(f"/p/{link.slug}/results/")
                items = response.context["runtime"]["review_items"]

                self.assertEqual([item["status"] for item in items], ["wrong", "unanswered", "unanswered"])
                self.assertEqual([item["is_correct"] for item in items], [False, None, None])
                # Not «Неверно»: the item was never answered, and it reads neutral.
                self.assertContains(response, ">Неверно</span>", count=1)
                self.assertContains(response, ">Без ответа</span>", count=2)
                self.assertContains(response, "Вы не ответили на это задание.", count=2)
                self.assertContains(response, 'data-review-status="unanswered"', count=2)
                self.assertContains(response, "player-review-card--unanswered")
                # Finishing early must not hand out the answers of the items never answered.
                self.assertContains(response, "Правильный ответ: ZZCORRECT 1")
                self.assertNotContains(response, "ZZCORRECT 2")
                self.assertNotContains(response, "ZZCORRECT 3")
                answered = next(card for card in response.context["player_shell"]["summary_cards"] if card["key"] == "answered")
                self.assertEqual((answered["value"], answered["suffix"]), ("1", "из 3"))

    def test_quiz_without_result_at_end_shows_only_the_total(self):
        link = self.publish(question_bank(2, show_result_at_end=False, reveal_correct_answer=True))
        response = self.run_to_results(link, {"q-1": "ZZCORRECT 1", "q-2": "ZZWRONG 2"})

        self.assertFalse(response.context["player_shell"]["shows_review"])
        self.assertEqual(response.context["runtime"]["review_items"], [])
        self.assertContains(response, 'data-results-copy="total"')
        self.assertContains(response, "доступен только итоговый результат")
        self.assertContains(response, "Только итог")
        self.assertContains(response, "Результат 50%")
        for text in ("разбор:", "Разберите", "Ваш ответ", "data-review-item", "ZZCORRECT", "ZZWRONG", "Повторите ошибки"):
            self.assertNotContains(response, text)

    def test_quiz_with_result_at_end_promises_and_shows_the_review(self):
        link = self.publish(question_bank(1, show_result_at_end=True, reveal_correct_answer=False))
        response = self.run_to_results(link, {"q-1": "ZZWRONG 1"})
        self.assertContains(response, 'data-results-copy="review"')
        self.assertContains(response, "Правильные ответы в этом интерактиве не показываются")
        self.assertContains(response, "data-review-item", count=1)


class ReviewLabelTests(PlayerPagesTestCase):
    def test_items_are_named_after_the_template(self):
        for template_key, label in REVIEW_LABELS.items():
            with self.subTest(template_key=template_key):
                link = self.publish(question_bank(2), template_key=template_key)
                response = self.run_to_results(link, {"q-1": "ZZCORRECT 1", "q-2": "ZZWRONG 2"})
                labels = [item["label"] for item in response.context["runtime"]["review_items"]]

                self.assertEqual(labels, [f"{label} 1", f"{label} 2"])
                self.assertContains(response, f">{label} 1<")
                if template_key != "quiz":
                    self.assertNotContains(response, "Вопрос 1")

    def test_cards_are_numbered_as_the_student_saw_them(self):
        link = self.publish(question_bank(6, shuffle=True), template_key="categorize")
        self.start(link)
        board = self.client.get(f"/p/{link.slug}/").context["runtime"]["cards"]
        board_order = [card["prompt"] for card in board]
        for card in board:
            self.answer(link, card["id"], f"ZZWRONG {card['id'].split('-')[1]}")

        items = self.client.get(f"/p/{link.slug}/results/").context["runtime"]["review_items"]

        self.assertEqual([item["prompt"] for item in items], board_order)
        self.assertEqual([item["label"] for item in items], [f"Карточка {card['number']}" for card in board])


class SnakeStartTests(PlayerPagesTestCase):
    template_key = "snake"

    def start_layer(self, response) -> str:
        match = re.search(r'<div class="snake-start" data-snake-start>.*?</button>', response.content.decode(), re.S)
        self.assertIsNotNone(match)
        return match.group(0)

    def test_the_snake_waits_for_start_and_a_resumed_run_for_continue(self):
        link = self.publish(question_bank(3))
        self.start(link)

        layer = self.start_layer(self.client.get(f"/p/{link.slug}/"))
        self.assertIn(">Начать<", layer)
        self.assertIn("Готовы?", layer)

        self.answer(link, "q-1", "ZZCORRECT 1")
        layer = self.start_layer(self.client.get(f"/p/{link.slug}/"))
        self.assertIn(">Продолжить<", layer)
        self.assertIn("Продолжаем: собрано 1 из 3", layer)

    def test_preview_has_the_start_layer_too(self):
        link = self.publish(question_bank(2))
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("activities:preview", args=[link.activity.pk]))
        self.assertIn(">Начать<", self.start_layer(response))
        self.assert_no_answer_key(response)
