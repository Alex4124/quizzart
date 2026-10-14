(() => {
    const { wait, submitAction, applyChoiceFeedback, finishIfComplete, focusFirst } = window.QuizzartPlayer;

    function initQuizPlayers() {
        document.querySelectorAll("[data-quiz-player]").forEach((root) => {
            const questions = Array.from(root.querySelectorAll("[data-quiz-question]"));
            if (!questions.length) {
                return;
            }

            function panelOf(question) {
                return question.querySelector(".quiz-card__content") || question;
            }

            function showQuestion(question) {
                questions.forEach((candidate) => {
                    const isCurrent = candidate === question;
                    candidate.hidden = !isCurrent;
                    candidate.classList.toggle("question-card-current", isCurrent);
                    panelOf(candidate).classList.remove("quiz-card-enter", "quiz-card-exit");
                });
                window.requestAnimationFrame(() => panelOf(question).classList.add("quiz-card-enter"));
                focusFirst(question);
            }

            questions.forEach((question) => {
                const form = question.querySelector("[data-answer-form]");
                if (!form) {
                    return;
                }
                const options = Array.from(form.querySelectorAll("button[name='answer']"));

                form.addEventListener("submit", async (event) => {
                    const chosen = event.submitter;
                    if (!chosen || chosen.name !== "answer") {
                        return;
                    }
                    event.preventDefault();
                    if (question.dataset.state === "answered") {
                        return;
                    }

                    const payload = await submitAction(form, { root, answer: chosen.value });
                    if (!payload?.feedback) {
                        return;
                    }

                    question.dataset.state = "answered";
                    const delay = applyChoiceFeedback(
                        options,
                        chosen,
                        payload.feedback,
                        form.querySelector("[data-question-feedback]"),
                    );
                    await wait(Math.max(120, delay - 180));
                    panelOf(question).classList.remove("quiz-card-enter");
                    panelOf(question).classList.add("quiz-card-exit");
                    await wait(180);

                    if (finishIfComplete(payload, root)) {
                        return;
                    }
                    const next = questions.find((candidate) => candidate.dataset.state !== "answered");
                    if (next) {
                        showQuestion(next);
                    }
                });
            });
        });
    }

    // One broken widget must not stop the rest of the page from initialising.
    [
        initQuizPlayers,
    ].forEach((init) => {
        try {
            init();
        } catch (error) {
            console.error(`[quizzart] ${init.name} failed`, error);
        }
    });
})();
