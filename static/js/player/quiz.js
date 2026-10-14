(() => {
    const { nativeSubmit, markSelectedOption, preserveSubmittedValue, revealChoiceState, enhanceAnswerForm, submitFormAsJson } = window.QuizzartPlayer;

    function initQuizPlayers() {
        document.querySelectorAll("[data-quiz-player]").forEach((root) => {
            const preview = root.dataset.preview === "1";
            const revealCorrect = root.dataset.revealCorrect === "1";
            const form = root.matches("form.quiz-flow") ? root : root.querySelector("form.quiz-flow");
            const submitButton = root.querySelector("[data-quiz-submit]");
            const completeMessage = root.querySelector("[data-preview-complete]");
            const questions = Array.from(root.querySelectorAll("[data-quiz-question]"));

            if (!form || !questions.length) {
                return;
            }

            if (submitButton) {
                submitButton.hidden = true;
            }

            function getAnimatedQuizPanel(question) {
                return question.querySelector(".quiz-card__content") || question;
            }

            function showQuestion(index) {
                questions.forEach((question, questionIndex) => {
                    const isCurrent = questionIndex === index;
                    const animatedPanel = getAnimatedQuizPanel(question);
                    question.hidden = !isCurrent;
                    question.classList.toggle("question-card-current", isCurrent);
                    question.classList.toggle("question-card-past", questionIndex < index);
                    animatedPanel.classList.remove("quiz-card-enter", "quiz-card-exit");
                    if (isCurrent) {
                        delete question.dataset.locked;
                        const feedback = question.querySelector("[data-question-feedback]");
                        if (feedback) {
                            feedback.hidden = true;
                            feedback.textContent = "";
                        }
                        window.requestAnimationFrame(() => animatedPanel.classList.add("quiz-card-enter"));
                    }
                });
            }

            showQuestion(0);

            questions.forEach((question, index) => {
                question.querySelectorAll("input[type='radio']").forEach((input) => {
                    input.addEventListener("change", () => {
                        if (question.dataset.locked === "1") {
                            return;
                        }

                        const animatedPanel = getAnimatedQuizPanel(question);
                        question.dataset.locked = "1";
                        markSelectedOption(input);
                        const delay = revealChoiceState(question, input, revealCorrect);

                        window.setTimeout(() => {
                            animatedPanel.classList.remove("quiz-card-enter");
                            animatedPanel.classList.add("quiz-card-exit");
                        }, Math.max(120, delay - 180));

                        window.setTimeout(() => {
                            if (index < questions.length - 1) {
                                showQuestion(index + 1);
                                return;
                            }

                            if (preview) {
                                if (completeMessage) {
                                    completeMessage.hidden = false;
                                }
                                return;
                            }

                            root.classList.add("player-shell-checking");
                            nativeSubmit.call(form);
                        }, delay);
                    });
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
