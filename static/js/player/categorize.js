(() => {
    const { nativeSubmit, markSelectedOption, preserveSubmittedValue, revealChoiceState, enhanceAnswerForm, submitFormAsJson } = window.QuizzartPlayer;

    function initCategorizePlayers() {
        document.querySelectorAll("[data-categorize-player]").forEach((root) => {
            const preview = root.dataset.preview === "1";
            const revealCorrect = root.dataset.revealCorrect === "1";
            const form = root.querySelector("[data-categorize-form]");
            const board = root.querySelector("[data-categorize-board]");
            const submitState = root.querySelector("[data-categorize-submit-state]");
            const completeMessage = root.querySelector("[data-preview-complete]");
            const cards = Array.from(root.querySelectorAll("[data-categorize-card]"));
            let activeCard = null;
            let isSubmitting = false;

            if (!form || !board || !cards.length) {
                return;
            }

            function applyChoiceState(card, buttons, selectedButton, feedback) {
                const correctOption = card.dataset.correctOption || "";
                const isCorrectAnswer = selectedButton.dataset.choiceValue === correctOption;

                buttons.forEach((button) => {
                    const isSelected = button === selectedButton;
                    const isCorrect = button.dataset.choiceValue === correctOption;
                    button.classList.toggle("is-selected", isSelected);
                    button.classList.toggle("is-correct", revealCorrect && isCorrect);
                    button.classList.toggle("is-wrong", revealCorrect && isSelected && !isCorrect);
                    button.disabled = true;
                });

                if (feedback) {
                    if (!revealCorrect) {
                        feedback.textContent = "Ответ сохранён.";
                    } else if (isCorrectAnswer) {
                        feedback.textContent = "Верно. Карточка засчитана.";
                    } else {
                        feedback.textContent = `Неверно. Правильный ответ: ${correctOption}`;
                    }
                    feedback.hidden = false;
                }

                return revealCorrect ? 980 : 220;
            }

            function updateBoardState() {
                board.classList.toggle("cards-board-has-active", Boolean(activeCard));
                cards.forEach((card) => {
                    const state = card.dataset.state || "closed";
                    const isActive = card === activeCard;
                    const isAnswered = state === "answered";
                    const isOpen = state === "open";
                    const isBlocked = Boolean(activeCard) && !isActive && !isAnswered;

                    card.classList.toggle("cards-card-closed", state === "closed");
                    card.classList.toggle("cards-card-open", isOpen);
                    card.classList.toggle("cards-card-answered", isAnswered);
                    card.classList.toggle("cards-card-blocked", isBlocked);

                    card.querySelectorAll("[data-categorize-choice]").forEach((button) => {
                        if (isAnswered) {
                            return;
                        }
                        button.disabled = !isActive;
                    });
                });
            }

            function finishFlow() {
                if (isSubmitting) {
                    return;
                }
                isSubmitting = true;
                activeCard = null;
                updateBoardState();
                if (preview) {
                    if (completeMessage) {
                        completeMessage.hidden = false;
                    }
                    return;
                }
                if (submitState) {
                    submitState.hidden = false;
                }
                root.classList.add("player-shell-checking");
                window.setTimeout(() => nativeSubmit.call(form), 320);
            }

            function openCard(card) {
                if (isSubmitting || activeCard || (card.dataset.state || "closed") !== "closed") {
                    return;
                }
                activeCard = card;
                card.dataset.state = "open";
                delete card.dataset.locked;
                const badge = card.querySelector("[data-categorize-badge]");
                if (badge) {
                    badge.textContent = "Открыта";
                }
                const feedback = card.querySelector("[data-question-feedback]");
                if (feedback) {
                    feedback.hidden = true;
                    feedback.textContent = "";
                }
                updateBoardState();
            }

            cards.forEach((card) => {
                card.addEventListener("click", (event) => {
                    if (event.target.closest("[data-categorize-choice]")) {
                        return;
                    }
                    openCard(card);
                });

                const buttons = Array.from(card.querySelectorAll("[data-categorize-choice]"));
                const feedback = card.querySelector("[data-question-feedback]");

                buttons.forEach((button) => {
                    button.addEventListener("click", (event) => {
                        event.stopPropagation();
                        if (
                            isSubmitting ||
                            activeCard !== card ||
                            card.dataset.locked === "1" ||
                            (card.dataset.state || "closed") !== "open"
                        ) {
                            return;
                        }

                        card.dataset.locked = "1";
                        const hiddenInput = form.querySelector(`[data-answer-target="${CSS.escape(card.dataset.itemId)}"]`);
                        if (hiddenInput) {
                            hiddenInput.value = button.dataset.choiceValue || "";
                        }

                        const delay = applyChoiceState(card, buttons, button, feedback);

                        window.setTimeout(() => {
                            card.dataset.state = "answered";
                            card.dataset.answered = "1";
                            const badge = card.querySelector("[data-categorize-badge]");
                            if (badge) {
                                badge.textContent = "Отвечено";
                            }
                            activeCard = null;
                            updateBoardState();

                            const allAnswered = cards.every(
                                (candidate) => (candidate.dataset.state || "closed") === "answered",
                            );
                            if (allAnswered) {
                                finishFlow();
                            }
                        }, delay);
                    });
                });
            });

            cards.forEach((card) => {
                if ((card.dataset.state || "closed") === "answered") {
                    const hiddenInput = form.querySelector(`[data-answer-target="${CSS.escape(card.dataset.itemId)}"]`);
                    const selectedValue = hiddenInput ? hiddenInput.value : "";
                    const buttons = Array.from(card.querySelectorAll("[data-categorize-choice]"));
                    const selectedButton = buttons.find((button) => button.dataset.choiceValue === selectedValue);
                    if (selectedButton) {
                        applyChoiceState(card, buttons, selectedButton, card.querySelector("[data-question-feedback]"));
                    } else {
                        buttons.forEach((button) => {
                            button.disabled = true;
                        });
                    }
                }
            });

            if (cards.every((card) => (card.dataset.state || "closed") === "answered")) {
                finishFlow();
                return;
            }
            updateBoardState();
        });
    }

    // One broken widget must not stop the rest of the page from initialising.
    [
        initCategorizePlayers,
    ].forEach((init) => {
        try {
            init();
        } catch (error) {
            console.error(`[quizzart] ${init.name} failed`, error);
        }
    });
})();
