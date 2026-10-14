(() => {
    const { nativeSubmit, markSelectedOption, preserveSubmittedValue, revealChoiceState, enhanceAnswerForm, submitFormAsJson } = window.QuizzartPlayer;

    function initMatchingPlayers() {
        document.querySelectorAll("[data-matching-player]").forEach((root) => {
            const preview = root.dataset.preview === "1";
            const form = root.querySelector("form.matching-flow");
            const submitButton = root.querySelector("[data-matching-submit]");
            const completeMessage = root.querySelector("[data-preview-complete]");
            const questions = Array.from(root.querySelectorAll("[data-matching-question]"));
            const choiceButtons = Array.from(root.querySelectorAll("[data-matching-choice]"));
            let currentIndex = 0;

            if (!form || !questions.length || !choiceButtons.length) {
                return;
            }

            if (submitButton) {
                submitButton.hidden = true;
            }

            function syncChoiceStates() {
                choiceButtons.forEach((button) => {
                    button.classList.remove("is-selected", "is-correct", "is-wrong", "matching-choice-correct");
                    button.hidden = false;
                    button.disabled = false;
                });
            }

            function resetQuestion(question) {
                if (!question) {
                    return;
                }

                delete question.dataset.locked;
                const dock = question.querySelector("[data-matching-dock]");
                const dockPlaceholder = question.querySelector("[data-matching-dock-placeholder]");
                const dockedCard = question.querySelector("[data-matching-docked-card]");
                const feedback = question.querySelector("[data-question-feedback]");

                if (dock) {
                    dock.hidden = false;
                    dock.classList.remove("matching-dock-staging", "matching-dock-filled");
                }
                if (dockPlaceholder) {
                    dockPlaceholder.hidden = false;
                }
                if (dockedCard) {
                    dockedCard.hidden = true;
                    dockedCard.textContent = "";
                    dockedCard.className = "matching-dock-card";
                }
                if (feedback) {
                    feedback.hidden = true;
                    feedback.textContent = "";
                }
            }

            function attachChoiceToDock(question, sourceButton, choiceText) {
                const dock = question?.querySelector("[data-matching-dock]");
                const dockPlaceholder = question?.querySelector("[data-matching-dock-placeholder]");
                const dockedCard = question?.querySelector("[data-matching-docked-card]");
                if (!dock || !dockedCard || !sourceButton) {
                    return 0;
                }

                dock.hidden = false;
                if (dockPlaceholder) {
                    dockPlaceholder.hidden = true;
                }
                dockedCard.className = "matching-dock-card option-row matching-choice matching-choice-docked";
                dockedCard.hidden = false;
                dockedCard.innerHTML = sourceButton.innerHTML;
                dockedCard.dataset.choiceValue = choiceText;
                dock.classList.add("matching-dock-filled");

                return 0;
            }

            function showQuestion(index) {
                currentIndex = index;
                questions.forEach((question, questionIndex) => {
                    const isCurrent = questionIndex === index;
                    question.hidden = !isCurrent;
                    question.classList.toggle("matching-card-current", isCurrent);
                    question.classList.remove("matching-card-enter", "matching-card-exit");
                    if (isCurrent) {
                        resetQuestion(question);
                        window.requestAnimationFrame(() => question.classList.add("matching-card-enter"));
                    }
                });
                syncChoiceStates();
            }

            function finishFlow() {
                if (preview) {
                    if (completeMessage) {
                        completeMessage.hidden = false;
                    }
                    return;
                }
                nativeSubmit.call(form);
            }

            choiceButtons.forEach((button) => {
                button.addEventListener("click", () => {
                    const question = questions[currentIndex];
                    const feedback = question?.querySelector("[data-question-feedback]");
                    if (!question || question.dataset.locked === "1") {
                        return;
                    }

                    question.dataset.locked = "1";
                    choiceButtons.forEach((candidate) => {
                        candidate.disabled = true;
                    });

                    const hiddenInput = form.querySelector(`[data-answer-target="${CSS.escape(question.dataset.itemId)}"]`);
                    const selectedValue = button.dataset.choiceValue || "";
                    if (hiddenInput) {
                        hiddenInput.value = selectedValue;
                    }

                    const correctOption = question.dataset.correctOption || "";
                    const correctChoiceId = question.dataset.correctChoiceId || "";
                    const correctButton =
                        choiceButtons.find((candidate) => candidate.dataset.choiceId === correctChoiceId) ||
                        choiceButtons.find((candidate) => candidate.dataset.choiceValue === correctOption);
                    const isCorrectAnswer =
                        button.dataset.choiceId === correctChoiceId || selectedValue === correctOption;

                    button.classList.add("is-selected");
                    button.classList.toggle("is-correct", isCorrectAnswer);
                    button.classList.toggle("is-wrong", !isCorrectAnswer);

                    if (feedback) {
                        feedback.textContent = isCorrectAnswer
                            ? "Верно. Карточка ответа присоединена."
                            : `Неверно. Правильная карточка: ${correctOption}`;
                        feedback.hidden = false;
                    }

                    const dockSource = isCorrectAnswer ? button : correctButton;
                    const movementDuration = attachChoiceToDock(
                        question,
                        dockSource,
                        correctOption,
                    );
                    const exitDelay = isCorrectAnswer ? 520 : 760;

                    window.setTimeout(() => {
                        button.classList.remove("is-selected", "is-correct", "is-wrong");
                        syncChoiceStates();
                        question.classList.remove("matching-card-enter");
                        question.classList.add("matching-card-exit");
                    }, Math.max(220, movementDuration + 80));

                    window.setTimeout(() => {
                        if (currentIndex < questions.length - 1) {
                            showQuestion(currentIndex + 1);
                            return;
                        }
                        finishFlow();
                    }, exitDelay);
                });
            });

            showQuestion(0);
        });
    }

    // One broken widget must not stop the rest of the page from initialising.
    [
        initMatchingPlayers,
    ].forEach((init) => {
        try {
            init();
        } catch (error) {
            console.error(`[quizzart] ${init.name} failed`, error);
        }
    });
})();
