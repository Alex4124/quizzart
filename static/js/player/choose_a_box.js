(() => {
    const { nativeSubmit, markSelectedOption, preserveSubmittedValue, revealChoiceState, enhanceAnswerForm, submitFormAsJson } = window.QuizzartPlayer;

    function initBoxPlayers() {
        document.querySelectorAll("[data-box-player]").forEach((root) => {
            const preview = root.dataset.preview === "1";
            const revealCorrect = root.dataset.revealCorrect === "1";
            const answeredCountTarget = root.querySelector("[data-box-answered-count]");
            const finishForm = root.querySelector("[data-box-finish-form]");
            const finishTrigger = root.querySelector("[data-box-finish-trigger]");
            const answerTargets = new Map();
            let answeredCount = Number.parseInt(root.dataset.answeredCount || "0", 10) || 0;
            const totalBoxes = Number.parseInt(root.dataset.totalBoxes || "0", 10) || 0;

            if (finishForm) {
                finishForm.querySelectorAll("[data-box-answer-target]").forEach((input) => {
                    answerTargets.set(input.dataset.boxAnswerTarget || "", input);
                });
            }

            function syncAnsweredCount(nextValue) {
                answeredCount = nextValue;
                if (answeredCountTarget) {
                    answeredCountTarget.textContent = String(answeredCount);
                }
                root.dataset.answeredCount = String(answeredCount);
            }

            function revealFinishControls() {
                if (finishForm) {
                    finishForm.hidden = false;
                }
                if (finishTrigger) {
                    finishTrigger.hidden = false;
                }
            }

            function submitFinishForm() {
                if (!finishForm || finishForm.dataset.submitting === "1") {
                    return;
                }

                finishForm.dataset.submitting = "1";
                root.classList.add("player-shell-checking");
                nativeSubmit.call(finishForm);
            }

            function openStudentBox(card) {
                const cover = card?.querySelector("[data-box-cover]");
                const panel = card?.querySelector("[data-box-question-panel]");
                const openForm = card?.querySelector("[data-box-open-form]");
                if (!card || !cover || !panel) {
                    return;
                }

                card.classList.remove("box-card-answered", "box-card-answering");
                card.classList.add("box-card-opening");

                window.setTimeout(() => {
                    card.classList.remove("box-card-opening");
                    card.classList.add("box-card-opened");
                    cover.hidden = true;
                    panel.hidden = false;
                    if (openForm) {
                        openForm.hidden = true;
                    }
                }, 280);
            }

            function finalizeStudentBox(form, selectedInput) {
                const card = form.closest("[data-box-card]");
                const questionPanel = card?.querySelector("[data-box-question-panel]");
                const resultPanel = card?.querySelector("[data-box-result-panel]");
                const answerTarget = resultPanel?.querySelector("[data-box-selected-answer]");
                const chip = resultPanel?.querySelector("[data-box-result-chip]");
                if (!card || !questionPanel || !resultPanel || !chip) {
                    return;
                }

                const itemId = form.dataset.itemId || "";
                const selectedValue = selectedInput?.value || "";
                const isCorrect = selectedValue === (form.dataset.correctOption || "");
                const wasAlreadyAnswered = form.dataset.answered === "1";
                const hiddenAnswerTarget = answerTargets.get(itemId);

                if (answerTarget) {
                    answerTarget.textContent = selectedValue || "\u041d\u0435\u0442 \u043e\u0442\u0432\u0435\u0442\u0430";
                }
                if (hiddenAnswerTarget) {
                    hiddenAnswerTarget.value = selectedValue;
                }

                chip.textContent = isCorrect ? "\u0412\u0435\u0440\u043d\u043e" : "\u041d\u0435\u0432\u0435\u0440\u043d\u043e";
                chip.classList.toggle("status-chip-published", isCorrect);
                chip.classList.toggle("status-chip-draft", !isCorrect);

                questionPanel.hidden = true;
                resultPanel.hidden = false;
                card.classList.remove("box-card-opened", "box-card-answering");
                card.classList.add("box-card-answered");
                form.dataset.answered = "1";

                if (!wasAlreadyAnswered) {
                    syncAnsweredCount(answeredCount + 1);
                }

                revealFinishControls();

                if (totalBoxes && answeredCount >= totalBoxes) {
                    window.setTimeout(() => submitFinishForm(), 360);
                }
            }

            if (preview) {
                root.querySelectorAll("[data-preview-open-box]").forEach((button) => {
                    button.addEventListener("click", () => {
                        const card = button.closest("[data-box-card]");
                        const cover = card?.querySelector("[data-box-cover]");
                        const panel = card?.querySelector("[data-preview-box-panel]");
                        if (!card || !panel || card.dataset.previewOpened === "1" || card.dataset.previewAnswered === "1") {
                            return;
                        }

                        card.dataset.previewOpened = "1";
                        card.classList.add("box-card-opening");

                        window.setTimeout(() => {
                            card.classList.remove("box-card-opening");
                            card.classList.add("box-card-opened");
                            if (cover) {
                                cover.hidden = true;
                            }
                            panel.hidden = false;
                            button.hidden = true;
                        }, 280);
                    });
                });
            }

            root.querySelectorAll("[data-box-open-form]").forEach((form) => {
                form.addEventListener("submit", (event) => {
                    if (preview) {
                        return;
                    }

                    event.preventDefault();
                    openStudentBox(form.closest("[data-box-card]"));
                });
            });

            root.querySelectorAll("[data-answer-form]").forEach((form) => {
                const isPreviewForm = form.dataset.preview === "1";
                if (preview !== isPreviewForm) {
                    return;
                }

                enhanceAnswerForm(form, revealCorrect, (input) => {
                    if (isPreviewForm) {
                        const card = form.closest("[data-box-card]");
                        const questionPanel = card?.querySelector("[data-preview-box-panel]");
                        const resultPanel = card?.querySelector("[data-preview-box-result]");
                        const answerTarget = resultPanel?.querySelector("[data-preview-selected-answer]");
                        const chip = resultPanel?.querySelector("[data-preview-result-chip]");
                        if (!card || !questionPanel || !resultPanel || !chip) {
                            return;
                        }

                        const selectedValue = input?.value || "";
                        const isCorrect = selectedValue === (form.dataset.correctOption || "");
                        if (answerTarget) {
                            answerTarget.textContent = selectedValue || "-";
                        }
                        chip.textContent = isCorrect ? "\u0412\u0435\u0440\u043d\u043e" : "\u041d\u0435\u0432\u0435\u0440\u043d\u043e";
                        chip.classList.toggle("status-chip-published", isCorrect);
                        chip.classList.toggle("status-chip-draft", !isCorrect);
                        questionPanel.hidden = true;
                        resultPanel.hidden = false;
                        card.classList.remove("box-card-opened");
                        card.classList.add("box-card-answered");
                        card.dataset.previewAnswered = "1";
                        return;
                    }

                    const card = form.closest("[data-box-card]");
                    if (card) {
                        card.classList.add("box-card-answering");
                    }
                    finalizeStudentBox(form, input);
                });
            });

            if (finishTrigger) {
                finishTrigger.addEventListener("submit", (event) => {
                    event.preventDefault();
                    submitFinishForm();
                });
            }
        });
    }

    // One broken widget must not stop the rest of the page from initialising.
    [
        initBoxPlayers,
    ].forEach((init) => {
        try {
            init();
        } catch (error) {
            console.error(`[quizzart] ${init.name} failed`, error);
        }
    });
})();
