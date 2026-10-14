(() => {
    // `parseInt(...) || fallback` would turn a deliberate 0 points into the default.
    function parsePoints(rawValue, fallback) {
        const parsed = Number.parseInt(String(rawValue ?? ""), 10);
        return Number.isNaN(parsed) ? fallback : parsed;
    }

    function parseQuestionBankItems(rawValue, defaultPoints) {
        if (!rawValue) {
            return [];
        }

        try {
            const parsed = JSON.parse(rawValue);
            if (!Array.isArray(parsed)) {
                return [];
            }
            return parsed.map((item) => ({
                prompt: typeof item?.prompt === "string" ? item.prompt : "",
                points: parsePoints(item?.points, defaultPoints),
                options: Array.isArray(item?.options)
                    ? item.options.map((option) => ({
                        text: typeof option?.text === "string" ? option.text : "",
                        is_correct: Boolean(option?.is_correct),
                    }))
                    : [],
            }));
        } catch (error) {
            return [];
        }
    }

    function initQuestionBankEditors() {
        document.querySelectorAll("[data-question-bank-editor]").forEach((root) => {
            const form = root.closest("form");
            const questionList = root.querySelector("[data-question-bank-list]");
            const questionTemplate = root.querySelector("[data-question-template]");
            const answerTemplate = root.querySelector("[data-answer-template]");
            const addQuestionButton = root.querySelector("[data-add-question]");
            const switchSubmit = form?.querySelector("[data-switch-template-submit]");
            const templateKeyInput = form?.querySelector("input[name='template_key']");
            const templateSwitch = document.querySelector("[data-template-switch]");
            const itemsJsonInput = form?.querySelector("input[name='items_json']");
            const itemsTextInput = form?.querySelector("input[name='items_text']");
            const disableScoringInput = form?.querySelector("input[name='disable_scoring']");
            const defaultPoints = Number.parseInt(root.dataset.defaultPoints || "10", 10) || 10;

            if (
                !form ||
                !questionList ||
                !questionTemplate ||
                !answerTemplate ||
                !addQuestionButton ||
                !itemsJsonInput
            ) {
                return;
            }

            function createEmptyQuestion() {
                return {
                    prompt: "",
                    points: defaultPoints,
                    options: [
                        { text: "", is_correct: true },
                        { text: "", is_correct: false },
                    ],
                };
            }

            function createEmptyAnswer() {
                return { text: "", is_correct: false };
            }

            function serializeItems() {
                const items = Array.from(questionList.querySelectorAll("[data-question-card]")).map((questionCard) => ({
                    prompt: questionCard.querySelector("[data-question-prompt]")?.value || "",
                    points: parsePoints(questionCard.querySelector("[data-question-points]")?.value, defaultPoints),
                    options: Array.from(questionCard.querySelectorAll("[data-answer-card]")).map((answerCard) => ({
                        text: answerCard.querySelector("[data-answer-text]")?.value || "",
                        is_correct: Boolean(answerCard.querySelector("[data-answer-correct]")?.checked),
                    })),
                }));

                itemsJsonInput.value = JSON.stringify(items);
                if (itemsTextInput) {
                    itemsTextInput.value = "";
                }
            }

            function syncScoringVisibility() {
                const scoringDisabled = Boolean(disableScoringInput?.checked);
                root.classList.toggle("is-scoring-disabled", scoringDisabled);
                root.querySelectorAll(".question-editor-points").forEach((pointsField) => {
                    pointsField.hidden = scoringDisabled;
                });
            }

            function syncTemplateKey() {
                if (templateKeyInput && templateSwitch) {
                    templateKeyInput.value = templateSwitch.value;
                }
            }

            function refreshQuestionLabels() {
                Array.from(questionList.querySelectorAll("[data-question-card]")).forEach((questionCard, questionIndex) => {
                    const title = questionCard.querySelector("[data-question-title]");
                    if (title) {
                        title.textContent = `Вопрос ${questionIndex + 1}`;
                    }

                    const answerCards = Array.from(questionCard.querySelectorAll("[data-answer-card]"));
                    answerCards.forEach((answerCard, answerIndex) => {
                        const answerTitle = answerCard.querySelector("[data-answer-title]");
                        const removeButton = answerCard.querySelector("[data-remove-answer]");
                        if (answerTitle) {
                            answerTitle.textContent = `Ответ ${answerIndex + 1}`;
                        }
                        if (removeButton) {
                            removeButton.hidden = answerCards.length <= 2;
                        }
                    });
                });
            }

            function appendAnswer(questionCard, answerData) {
                const answerList = questionCard.querySelector("[data-answer-list]");
                if (!answerList) {
                    return;
                }

                const fragment = answerTemplate.content.cloneNode(true);
                const answerCard = fragment.querySelector("[data-answer-card]");
                const textInput = fragment.querySelector("[data-answer-text]");
                const correctInput = fragment.querySelector("[data-answer-correct]");
                const removeButton = fragment.querySelector("[data-remove-answer]");

                if (!answerCard || !textInput || !correctInput || !removeButton) {
                    return;
                }

                textInput.value = answerData.text || "";
                correctInput.checked = Boolean(answerData.is_correct);

                textInput.addEventListener("input", serializeItems);
                correctInput.addEventListener("change", () => {
                    if (correctInput.checked) {
                        answerList.querySelectorAll("[data-answer-correct]").forEach((input) => {
                            if (input !== correctInput) {
                                input.checked = false;
                            }
                        });
                    }
                    serializeItems();
                });
                removeButton.addEventListener("click", () => {
                    if (answerList.querySelectorAll("[data-answer-card]").length <= 2) {
                        return;
                    }
                    answerCard.remove();
                    refreshQuestionLabels();
                    serializeItems();
                });

                answerList.appendChild(fragment);
                refreshQuestionLabels();
            }

            function appendQuestion(questionData, focusPrompt) {
                const normalizedQuestion = {
                    prompt: questionData?.prompt || "",
                    points: parsePoints(questionData?.points, defaultPoints),
                    options: Array.isArray(questionData?.options) && questionData.options.length
                        ? questionData.options.map((option) => ({
                            text: typeof option?.text === "string" ? option.text : "",
                            is_correct: Boolean(option?.is_correct),
                        }))
                        : [createEmptyAnswer(), createEmptyAnswer()],
                };

                while (normalizedQuestion.options.length < 2) {
                    normalizedQuestion.options.push(createEmptyAnswer());
                }

                const hasCorrectAnswer = normalizedQuestion.options.some((option) => option.is_correct);
                if (!hasCorrectAnswer) {
                    normalizedQuestion.options[0].is_correct = true;
                }

                const fragment = questionTemplate.content.cloneNode(true);
                const questionCard = fragment.querySelector("[data-question-card]");
                const promptInput = fragment.querySelector("[data-question-prompt]");
                const pointsInput = fragment.querySelector("[data-question-points]");
                const addAnswerInside = fragment.querySelector("[data-add-answer]");
                const removeQuestionButton = fragment.querySelector("[data-remove-question]");

                if (!questionCard || !promptInput || !pointsInput || !addAnswerInside || !removeQuestionButton) {
                    return;
                }

                promptInput.value = normalizedQuestion.prompt;
                pointsInput.value = String(normalizedQuestion.points);

                promptInput.addEventListener("input", serializeItems);
                pointsInput.addEventListener("input", serializeItems);
                addAnswerInside.addEventListener("click", () => {
                    appendAnswer(questionCard, createEmptyAnswer());
                    serializeItems();
                });
                removeQuestionButton.addEventListener("click", () => {
                    questionCard.remove();
                    if (!questionList.querySelector("[data-question-card]")) {
                        appendQuestion(createEmptyQuestion(), false);
                    }
                    refreshQuestionLabels();
                    serializeItems();
                });

                questionList.appendChild(fragment);

                normalizedQuestion.options.forEach((option) => appendAnswer(questionCard, option));
                refreshQuestionLabels();
                syncScoringVisibility();
                serializeItems();

                if (focusPrompt) {
                    promptInput.focus();
                }
            }

            const initialItems = parseQuestionBankItems(itemsJsonInput.value, defaultPoints);
            if (initialItems.length) {
                initialItems.forEach((item, index) => appendQuestion(item, index === initialItems.length - 1 && !item.prompt));
            } else {
                appendQuestion(createEmptyQuestion(), false);
            }

            addQuestionButton.addEventListener("click", () => {
                appendQuestion(createEmptyQuestion(), true);
            });

            disableScoringInput?.addEventListener("change", syncScoringVisibility);
            syncScoringVisibility();

            form.addEventListener("submit", () => {
                syncTemplateKey();
                serializeItems();
            });

            if (templateSwitch && templateKeyInput && switchSubmit) {
                templateSwitch.addEventListener("change", () => {
                    syncTemplateKey();
                    serializeItems();
                    switchSubmit.click();
                });
            }
        });
    }

    // One broken widget must not stop the rest of the page from initialising.
    [
        initQuestionBankEditors,
    ].forEach((init) => {
        try {
            init();
        } catch (error) {
            console.error(`[quizzart] ${init.name} failed`, error);
        }
    });
})();
