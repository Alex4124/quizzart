(() => {
    const nativeSubmit = HTMLFormElement.prototype.submit;

    function markSelectedOption(input) {
        const group = input.closest(".option-list");
        if (!group) {
            return;
        }
        group.querySelectorAll(".option-row").forEach((row) => row.classList.remove("is-selected"));
        const row = input.closest(".option-row");
        if (row) {
            row.classList.add("is-selected");
        }
        const card = input.closest(".question-card, .box-card");
        if (card) {
            card.classList.add("card-selected");
        }
    }

    function updateSelectState(select) {
        const card = select.closest(".question-card");
        if (!card) {
            return;
        }
        card.classList.toggle("card-selected", Boolean(select.value));
    }

    function preserveSubmittedValue(selectedInput) {
        const form = selectedInput.form || selectedInput.closest("form");
        const inputName = selectedInput.name;
        if (!form || !inputName) {
            return;
        }

        let mirror = Array.from(form.querySelectorAll("input[type='hidden'][data-preserved-answer]")).find(
            (candidate) => candidate.dataset.preservedAnswer === inputName,
        );
        if (!mirror) {
            mirror = document.createElement("input");
            mirror.type = "hidden";
            mirror.name = inputName;
            mirror.dataset.preservedAnswer = inputName;
            form.appendChild(mirror);
        }
        mirror.value = selectedInput.value;
    }

    function revealChoiceState(scope, selectedInput, revealCorrect) {
        const correctOption = scope.dataset.correctOption || "";
        const feedback = scope.querySelector("[data-question-feedback]");
        const isCorrectAnswer = selectedInput.value === correctOption;

        preserveSubmittedValue(selectedInput);

        scope.querySelectorAll(".option-row").forEach((row) => {
            const input = row.querySelector("input[type='radio']");
            if (!input) {
                return;
            }
            const isCorrect = input.value === correctOption;
            const isSelected = input === selectedInput;

            row.classList.toggle("is-selected", isSelected);
            row.classList.toggle("is-correct", (isSelected && isCorrect) || (revealCorrect && isCorrect));
            row.classList.toggle("is-wrong", revealCorrect && isSelected && !isCorrect);
            if (!revealCorrect) {
                row.classList.toggle("is-wrong", isSelected && !isCorrect);
            }
            input.disabled = true;
        });

        if (feedback) {
            if (isCorrectAnswer) {
                feedback.textContent = "Верно. Ответ засчитан.";
            } else if (revealCorrect) {
                feedback.textContent = `Неверно. Правильный ответ: ${correctOption}`;
            } else {
                feedback.textContent = "Неверно.";
            }
            feedback.hidden = false;
        }

        return revealCorrect ? 950 : 180;
    }

    function resetButtonRowState(buttons) {
        buttons.forEach((button) => {
            button.classList.remove(
                "is-selected",
                "is-correct",
                "is-wrong",
                "matching-choice-correct",
                "categorize-choice-moving",
                "categorize-choice-source-hidden",
            );
            button.disabled = false;
        });
    }

    function revealButtonChoiceState(buttons, selectedButton, correctOption, revealCorrect, feedback) {
        const isCorrectAnswer = selectedButton.dataset.choiceValue === correctOption;
        buttons.forEach((button) => {
            const isCorrect = button.dataset.choiceValue === correctOption;
            const isSelected = button === selectedButton;
            button.classList.toggle("is-selected", isSelected);
            button.classList.toggle("is-correct", (isSelected && isCorrect) || (revealCorrect && isCorrect));
            button.classList.toggle("is-wrong", isSelected && !isCorrect);
            button.classList.toggle("matching-choice-correct", revealCorrect && !isSelected && isCorrect);
            button.disabled = true;
        });

        if (feedback) {
            if (isCorrectAnswer) {
                feedback.textContent = "Верно. Ответ засчитан.";
            } else if (revealCorrect) {
                feedback.textContent = `Неверно. Правильный ответ: ${correctOption}`;
            } else {
                feedback.textContent = "Неверно.";
            }
            feedback.hidden = false;
        }

        return revealCorrect ? 950 : 220;
    }

    function animateCloneToTarget(
        source,
        target,
        cloneClassName,
        sourceHiddenClassName = "categorize-choice-source-hidden",
    ) {
        if (!source || !target) {
            return 0;
        }

        const sourceRect = source.getBoundingClientRect();
        const targetRect = target.getBoundingClientRect();
        if (!sourceRect.width || !targetRect.width || !targetRect.height) {
            return 0;
        }

        const clone = source.cloneNode(true);
        clone.classList.add(cloneClassName);
        clone.setAttribute("aria-hidden", "true");
        clone.style.left = `${sourceRect.left}px`;
        clone.style.top = `${sourceRect.top}px`;
        clone.style.width = `${sourceRect.width}px`;
        clone.style.height = `${sourceRect.height}px`;
        document.body.appendChild(clone);

        source.classList.add(sourceHiddenClassName);

        const deltaX = targetRect.left - sourceRect.left;
        const deltaY = targetRect.top - sourceRect.top;
        const scaleX = targetRect.width / sourceRect.width;
        const scaleY = targetRect.height / sourceRect.height;
        const duration = 520;

        window.requestAnimationFrame(() => {
            clone.style.transform = `translate(${deltaX}px, ${deltaY}px) scale(${scaleX}, ${scaleY})`;
            clone.style.opacity = "0.92";
        });

        window.setTimeout(() => {
            clone.remove();
            source.classList.remove(sourceHiddenClassName);
        }, duration);

        return duration;
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
                points: Number.parseInt(String(item?.points ?? defaultPoints), 10) || defaultPoints,
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
            const defaultPoints = Number.parseInt(root.dataset.defaultPoints || "1", 10) || 1;

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
                    points: Number.parseInt(
                        questionCard.querySelector("[data-question-points]")?.value || String(defaultPoints),
                        10,
                    ) || defaultPoints,
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
                    points: Number.parseInt(String(questionData?.points ?? defaultPoints), 10) || defaultPoints,
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

    function initRevealStagger() {
        document.querySelectorAll("[data-reveal-stagger]").forEach((element, index) => {
            element.style.setProperty("--stagger-index", String(index));
            element.classList.add("reveal-ready");
        });
    }

    function initOptionSelection() {
        document.querySelectorAll(".option-row input[type='radio']").forEach((input) => {
            if (input.checked) {
                markSelectedOption(input);
            }
            input.addEventListener("change", () => markSelectedOption(input));
        });
    }

    function initSelects() {
        document.querySelectorAll("select").forEach((select) => {
            updateSelectState(select);
            select.addEventListener("change", () => updateSelectState(select));
        });
    }

    function initDelayedSubmitForms() {
        document.querySelectorAll("form[data-delay-submit]").forEach((form) => {
            form.addEventListener("submit", (event) => {
                if (form.dataset.submitting === "1") {
                    return;
                }

                const delay = Number.parseInt(form.dataset.delaySubmit || "0", 10);
                if (!delay) {
                    return;
                }

                event.preventDefault();
                form.dataset.submitting = "1";

                const selector = form.dataset.animateTarget || "";
                const animateClass = form.dataset.animateClass || "card-selected";
                const target = selector ? form.closest(selector) || document.querySelector(selector) : form;
                if (target) {
                    target.classList.add(animateClass);
                }

                window.setTimeout(() => nativeSubmit.call(form), delay);
            });
        });
    }

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

    function enhanceAnswerForm(form, revealCorrect, onComplete) {
        const submitButton = form.querySelector("[data-answer-submit]");
        if (submitButton) {
            submitButton.hidden = true;
        }

        form.querySelectorAll("input[type='radio']").forEach((input) => {
            input.addEventListener("change", () => {
                if (form.dataset.locked === "1") {
                    return;
                }

                form.dataset.locked = "1";
                markSelectedOption(input);
                const delay = revealChoiceState(form, input, revealCorrect);

                window.setTimeout(() => onComplete(input), delay);
            });
        });
    }

    async function submitFormAsJson(form) {
        const response = await fetch(form.action || window.location.href, {
            method: (form.method || "post").toUpperCase(),
            headers: {
                Accept: "application/json",
                "X-Requested-With": "XMLHttpRequest",
            },
            body: new FormData(form),
            credentials: "same-origin",
        });

        const contentType = response.headers.get("content-type") || "";
        if (!contentType.includes("application/json")) {
            throw new Error("unexpected_response");
        }

        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(payload.error || "request_failed");
        }
        return payload;
    }

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

    function initWheelPlayers() {
        document.querySelectorAll("[data-wheel-player]").forEach((root) => {
            const preview = root.dataset.preview === "1";
            const revealCorrect = root.dataset.revealCorrect === "1";
            const noRepeat = root.dataset.noRepeat === "1";
            const playerShell = root.closest(".student-player") || root;
            const disc = root.querySelector("[data-wheel-disc]");
            const startButton = root.querySelector("[data-wheel-start]");
            const stopButton = root.querySelector("[data-wheel-stop]");
            const completeMessage = root.querySelector("[data-wheel-preview-complete]");
            const sectors = Array.from(root.querySelectorAll("[data-wheel-sector]"));
            const questions = Array.from(root.querySelectorAll("[data-wheel-question]"));
            const questionStack = root.querySelector(".wheel-question-stack");
            const spotlightTitle = root.querySelector("[data-wheel-spotlight-title]");
            const spotlightText = root.querySelector("[data-wheel-spotlight-text]");
            const summaryScore = playerShell.querySelector('[data-player-summary-value="score"]');
            const summaryProgress = playerShell.querySelector('[data-player-summary-value="progress"]');
            const factsAnswered = playerShell.querySelector('[data-player-fact-value="answered"]');
            const factsRemaining = playerShell.querySelector('[data-player-fact-value="remaining"]');
            const progressHeading = playerShell.querySelector("[data-player-progress-heading]");
            const progressRing = playerShell.querySelector("[data-player-progress-ring]");
            const progressRingLabel = playerShell.querySelector("[data-player-progress-ring-label]");
            const progressBarFill = playerShell.querySelector("[data-player-progress-bar-fill]");
            const progressSegments = Array.from(playerShell.querySelectorAll("[data-player-progress-segment]"));

            if (!disc || !startButton || !stopButton || !sectors.length) {
                return;
            }

            let rotation = 0;
            let spinning = false;
            let activeItemId = root.dataset.activeItem || "";
            let spinTimer = null;
            let currentScore = Number.parseInt(summaryScore?.textContent || "0", 10) || 0;
            let questionStackMinHeight = questionStack?.getBoundingClientRect().height || 0;
            const wheelQuestionExitDelay = 260;
            const answeredItems = new Set(
                sectors
                    .filter((sector) => sector.dataset.answered === "1")
                    .map((sector) => sector.dataset.itemId || ""),
            );
            const scrollStateKey = `quizzart-wheel-scroll:${window.location.pathname}`;

            function rememberScrollPosition() {
                try {
                    window.sessionStorage.setItem(scrollStateKey, String(window.scrollY));
                } catch (error) {
                    // Ignore sessionStorage failures and keep the flow working.
                }
            }

            function clearRememberedScrollPosition() {
                try {
                    window.sessionStorage.removeItem(scrollStateKey);
                } catch (error) {
                    // Ignore sessionStorage failures and keep the flow working.
                }
            }

            function restoreRememberedScrollPosition() {
                try {
                    const rawValue = window.sessionStorage.getItem(scrollStateKey);
                    if (!rawValue) {
                        return;
                    }

                    const savedScrollY = Number.parseInt(rawValue, 10);
                    window.sessionStorage.removeItem(scrollStateKey);
                    if (Number.isNaN(savedScrollY)) {
                        return;
                    }

                    window.requestAnimationFrame(() => {
                        window.scrollTo({ top: savedScrollY, behavior: "auto" });
                        window.requestAnimationFrame(() => {
                            window.scrollTo({ top: savedScrollY, behavior: "auto" });
                        });
                    });
                } catch (error) {
                    // Ignore sessionStorage failures and keep the flow working.
                }
            }

            function updateQuestionStackHeight() {
                if (!questionStack) {
                    return;
                }

                window.requestAnimationFrame(() => {
                    const currentHeight = questionStack.getBoundingClientRect().height;
                    questionStackMinHeight = Math.max(questionStackMinHeight, currentHeight);
                    if (questionStackMinHeight > 0) {
                        questionStack.style.minHeight = `${Math.ceil(questionStackMinHeight)}px`;
                    }
                });
            }

            function resetWheelQuestionAnimation(question) {
                if (!question) {
                    return;
                }

                question.classList.remove("wheel-question-card-enter", "wheel-question-card-exit");
            }

            function animateWheelQuestionIn(question) {
                if (!question) {
                    return;
                }

                resetWheelQuestionAnimation(question);
                question.hidden = false;
                window.requestAnimationFrame(() => {
                    question.classList.add("wheel-question-card-enter");
                });
            }

            function animateWheelQuestionOut(question) {
                if (!question || question.hidden) {
                    return Promise.resolve();
                }

                resetWheelQuestionAnimation(question);
                question.classList.add("wheel-question-card-exit");

                return new Promise((resolve) => {
                    window.setTimeout(() => {
                        question.hidden = true;
                        question.classList.remove("wheel-question-card-exit");
                        resolve();
                    }, wheelQuestionExitDelay);
                });
            }

            function preserveViewport(anchor, previousScrollY, previousTop) {
                if (!anchor) {
                    return;
                }

                const restore = () => {
                    const nextTop = anchor.getBoundingClientRect().top;
                    const nextScrollY = previousScrollY + (nextTop - previousTop);
                    window.scrollTo({ top: nextScrollY, behavior: "auto" });
                };

                window.requestAnimationFrame(() => {
                    restore();
                    window.requestAnimationFrame(restore);
                });
            }

            function syncHud() {
                const totalItems = sectors.length;
                const answeredCount = answeredItems.size;
                const remainingCount = Math.max(totalItems - answeredCount, 0);
                const progressPercent = totalItems ? Math.round((answeredCount / totalItems) * 100) : 0;
                const filledSegments = Math.max(0, Math.min(progressSegments.length, Math.round(progressPercent / 20)));

                if (summaryScore) {
                    summaryScore.textContent = String(currentScore);
                }
                if (summaryProgress) {
                    summaryProgress.textContent = `${progressPercent}%`;
                }
                if (factsAnswered) {
                    factsAnswered.textContent = totalItems ? `${answeredCount} из ${totalItems}` : "0";
                }
                if (factsRemaining) {
                    factsRemaining.textContent = String(remainingCount);
                }
                if (progressHeading) {
                    progressHeading.textContent = `${progressPercent}% готово`;
                }
                if (progressRing) {
                    progressRing.style.setProperty("--progress", String(progressPercent));
                }
                if (progressRingLabel) {
                    progressRingLabel.textContent = `${progressPercent}%`;
                }
                if (progressBarFill) {
                    progressBarFill.style.width = `${progressPercent}%`;
                }
                progressSegments.forEach((segment, index) => {
                    segment.classList.toggle("is-filled", index < filledSegments);
                });
            }

            function syncSpotlight() {
                if (!spotlightTitle || !spotlightText) {
                    return;
                }

                if (activeItemId) {
                    spotlightTitle.textContent = "Готовы к новому испытанию?";
                    spotlightText.textContent = "Выберите верный вариант ответа после остановки колеса.";
                    return;
                }

                spotlightTitle.textContent = "Крутите колесо, чтобы получить вопрос";
                spotlightText.textContent = "Каждый сектор открывает отдельный вопрос и сохраняет результат после ответа.";
            }

            const questionMap = new Map();
            questions.forEach((question) => {
                questionMap.set(question.dataset.itemId || "", question);
                const form = question.querySelector("[data-answer-form]");
                if (!form) {
                    return;
                }

                if (!preview) {
                    form.addEventListener("submit", (event) => {
                        event.preventDefault();
                    });
                }

                enhanceAnswerForm(form, revealCorrect, async () => {
                    const itemId = question.dataset.itemId || "";
                    if (preview) {
                        answeredItems.add(itemId);
                        const sector = sectors.find((candidate) => candidate.dataset.itemId === itemId);
                        if (sector) {
                            sector.dataset.answered = "1";
                            sector.classList.add("wheel-sector-answered");
                            sector.classList.remove("wheel-sector-active");
                        }
                        await animateWheelQuestionOut(question);
                        activeItemId = "";
                        syncHud();
                        syncSpotlight();
                        updateQuestionStackHeight();
                        updateControlState();
                        if (!getAvailableSectors().length && completeMessage) {
                            completeMessage.hidden = false;
                        }
                        return;
                    }

                    const preservedScrollY = window.scrollY;
                    const preservedAnchor = root.closest(".student-player__layout") || root;
                    const preservedAnchorTop = preservedAnchor.getBoundingClientRect().top;
                    const activeElement = document.activeElement;
                    if (activeElement instanceof HTMLElement) {
                        activeElement.blur();
                    }

                    try {
                        rememberScrollPosition();
                        playerShell.classList.add("player-shell-checking");
                        const payload = await submitFormAsJson(form);
                        currentScore = Number.parseInt(String(payload.score ?? currentScore), 10) || 0;
                        answeredItems.add(itemId);

                        const sector = sectors.find((candidate) => candidate.dataset.itemId === itemId);
                        if (sector) {
                            sector.dataset.answered = "1";
                            sector.classList.add("wheel-sector-answered");
                            sector.classList.remove("wheel-sector-active");
                        }

                        await animateWheelQuestionOut(question);
                        activeItemId = "";
                        syncHud();
                        syncSpotlight();
                        updateQuestionStackHeight();
                        updateControlState();
                        preserveViewport(preservedAnchor, preservedScrollY, preservedAnchorTop);

                        if (payload.is_complete && payload.redirect_url) {
                            window.location.assign(payload.redirect_url);
                            return;
                        }
                        clearRememberedScrollPosition();
                    } catch (error) {
                        nativeSubmit.call(form);
                    } finally {
                        playerShell.classList.remove("player-shell-checking");
                    }
                });
            });

            function applyRotation(value) {
                disc.style.transform = `rotate(${value}deg)`;
            }

            function layoutWheelLabels() {
                const discSize = disc.getBoundingClientRect().width;
                if (!discSize || !sectors.length) {
                    return;
                }

                const radius = discSize / 2;
                const outerRadius = radius - 8;
                const innerRadius = radius * 0.16;
                const sectorAngle = (Math.PI * 2) / sectors.length;
                const sectorSizeDegrees = 360 / sectors.length;
                const centroidRadius = (4 * outerRadius * Math.sin(sectorAngle / 2)) / (3 * sectorAngle);
                const labelRadius = Math.min(outerRadius * 0.68, Math.max(outerRadius * 0.46, centroidRadius * 0.96));
                const sectorChord = 2 * labelRadius * Math.sin(sectorAngle / 2);
                const radialRoom = 2 * Math.min(labelRadius - innerRadius, outerRadius - labelRadius);
                const labelWidth = Math.max(66, Math.min(radialRoom * 0.92, sectorChord * 0.94, outerRadius * 0.72));
                const promptSize = Math.max(0.54, Math.min(1.04, 0.42 + (labelWidth / 240)));
                const labelLines = sectorSizeDegrees < 46 ? 2 : 3;

                disc.style.setProperty("--wheel-label-radius", `${labelRadius.toFixed(1)}px`);
                disc.style.setProperty("--wheel-label-width", `${labelWidth.toFixed(1)}px`);
                disc.style.setProperty("--wheel-prompt-size", `${promptSize.toFixed(3)}rem`);
                disc.style.setProperty("--wheel-label-lines", String(labelLines));

                sectors.forEach((sector, sectorIndex) => {
                    const centerAngle = -90 + sectorIndex * sectorSizeDegrees;
                    const labelRotation = 180;

                    sector.style.setProperty("--wheel-sector-center-angle", `${centerAngle.toFixed(3)}deg`);
                    sector.style.setProperty("--wheel-label-rotation", `${labelRotation.toFixed(3)}deg`);
                });
            }

            function getAvailableSectors() {
                return sectors.filter((sector) => !noRepeat || !answeredItems.has(sector.dataset.itemId || ""));
            }

            function showQuestion(itemId) {
                activeItemId = itemId;
                questions.forEach((question) => {
                    const isCurrent = question.dataset.itemId === itemId;
                    if (isCurrent) {
                        animateWheelQuestionIn(question);
                        return;
                    }

                    resetWheelQuestionAnimation(question);
                    question.hidden = true;
                });
                sectors.forEach((sector) => {
                    sector.classList.toggle("wheel-sector-active", sector.dataset.itemId === itemId);
                });
                syncSpotlight();
                updateQuestionStackHeight();
                updateControlState();
            }

            function updateControlState() {
                const hasAvailable = getAvailableSectors().length > 0;
                const hasActive = Boolean(activeItemId);
                startButton.disabled = spinning || hasActive || !hasAvailable;
                stopButton.disabled = !spinning;
            }

            function startSpin() {
                if (spinning || activeItemId || !getAvailableSectors().length) {
                    return;
                }

                spinning = true;
                disc.classList.add("wheel-disc-live");
                disc.style.transition = "none";
                spinTimer = window.setInterval(() => {
                    rotation += 10;
                    applyRotation(rotation);
                }, 16);
                updateControlState();
            }

            function stopSpin() {
                if (!spinning) {
                    return;
                }

                spinning = false;
                window.clearInterval(spinTimer);
                const available = getAvailableSectors();
                if (!available.length) {
                    updateControlState();
                    return;
                }

                const chosen = available[Math.floor(Math.random() * available.length)];
                const sectorCount = sectors.length;
                const sectorSize = 360 / sectorCount;
                const sectorIndex = Number.parseInt(chosen.dataset.sectorIndex || "0", 10);
                // The player visual uses a left-side pointer, which maps to the 180deg stopping angle.
                const pointerAngle = 180;
                const sectorCenterAngle = -90 + sectorIndex * sectorSize;
                const targetAngle = pointerAngle - sectorCenterAngle;
                const normalizedRotation = ((rotation % 360) + 360) % 360;
                const delta = ((targetAngle - normalizedRotation) + 360) % 360;

                rotation += 1440 + delta;
                disc.style.transition = "transform 1.2s cubic-bezier(0.18, 0.8, 0.2, 1)";
                applyRotation(rotation);

                window.setTimeout(() => {
                    disc.classList.remove("wheel-disc-live");
                    showQuestion(chosen.dataset.itemId || "");
                }, 1200);

                updateControlState();
            }

            startButton.addEventListener("click", startSpin);
            stopButton.addEventListener("click", stopSpin);
            layoutWheelLabels();
            window.addEventListener("resize", layoutWheelLabels);

            if (activeItemId) {
                showQuestion(activeItemId);
            } else {
                questions.forEach((question) => {
                    question.hidden = true;
                });
                syncHud();
                syncSpotlight();
                updateQuestionStackHeight();
                updateControlState();
            }

            restoreRememberedScrollPosition();
        });
    }

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
                    const isUsed = button.dataset.used === "1";
                    button.classList.remove("is-selected", "is-correct", "is-wrong", "matching-choice-correct");
                    button.classList.toggle("matching-choice-used", isUsed);
                    button.hidden = isUsed;
                    button.disabled = isUsed;
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

                    const hiddenInput = form.querySelector(`[data-answer-target="${question.dataset.itemId}"]`);
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
                    if (correctButton) {
                        correctButton.dataset.used = "1";
                    }

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
                        const hiddenInput = form.querySelector(`[data-answer-target="${card.dataset.itemId}"]`);
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
                    const hiddenInput = form.querySelector(`[data-answer-target="${card.dataset.itemId}"]`);
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

    function initSnakePlayers() {
        const directionVectors = {
            up: { x: 0, y: -1 },
            right: { x: 1, y: 0 },
            down: { x: 0, y: 1 },
            left: { x: -1, y: 0 },
        };
        const directionKeys = {
            ArrowUp: "up",
            ArrowRight: "right",
            ArrowDown: "down",
            ArrowLeft: "left",
        };

        document.querySelectorAll("[data-snake-player]").forEach((root) => {
            const preview = root.dataset.preview === "1";
            const revealCorrect = root.dataset.revealCorrect === "1";
            const board = root.querySelector("[data-snake-board]");
            const playfield = root.querySelector("[data-snake-playfield]");
            const head = root.querySelector("[data-snake-head]");
            const segmentHost = root.querySelector("[data-snake-segments]");
            const questionLayer = root.querySelector("[data-snake-question-layer]");
            const submitForm = root.querySelector("[data-snake-submit-form]");
            const submitState = root.querySelector("[data-snake-submit-state]");
            const completeMessage = root.querySelector("[data-snake-preview-complete]");
            const progressValue = root.querySelector("[data-snake-progress]");
            const remainingValue = root.querySelector("[data-snake-remaining]");
            const scoreValue = root.querySelector("[data-snake-score]");
            const appleElements = Array.from(root.querySelectorAll("[data-snake-apple]"));
            const questionCards = Array.from(root.querySelectorAll("[data-snake-question-card]"));
            const directionButtons = Array.from(root.querySelectorAll("[data-snake-direction]"));

            if (
                !board ||
                !playfield ||
                !head ||
                !segmentHost ||
                !questionLayer ||
                !submitForm ||
                !appleElements.length ||
                !questionCards.length
            ) {
                return;
            }

            const appleMap = new Map();
            appleElements.forEach((apple) => {
                appleMap.set(apple.dataset.itemId || "", apple);
            });

            const questionMap = new Map();
            questionCards.forEach((card) => {
                questionMap.set(card.dataset.itemId || "", card);
            });

            const answerTargets = new Map();
            submitForm.querySelectorAll("[data-answer-target]").forEach((input) => {
                answerTargets.set(input.dataset.answerTarget || "", input);
            });

            let frameId = null;
            let boardRect = null;
            let paused = false;
            let completed = false;
            let answeredCount = 0;
            let localScore = Number.parseInt(root.dataset.initialScore || "0", 10) || 0;
            let activeItemId = "";
            let lastTimestamp = 0;
            let headPoint = { x: 0, y: 0 };
            let heading = { x: 1, y: 0 };
            let queuedHeading = null;
            const bodyPoints = [];
            const segments = [];
            const baseSegmentCount = 5;
            const totalItems = appleElements.length;
            const headRadius = 20;
            const segmentRadius = 14;
            const beaconRadius = 22;
            const contactOverlap = 2;
            const headSegmentDistance = headRadius + segmentRadius - contactOverlap;
            const segmentDistance = segmentRadius + segmentRadius - contactOverlap;

            function clamp(value, min, max) {
                return Math.min(max, Math.max(min, value));
            }

            function distance(first, second) {
                return Math.hypot(first.x - second.x, first.y - second.y);
            }

            function normalizeVector(dx, dy, fallback) {
                const vectorLength = Math.hypot(dx, dy);
                if (vectorLength > 0.0001) {
                    return {
                        x: dx / vectorLength,
                        y: dy / vectorLength,
                    };
                }
                return fallback;
            }

            function movementSpeed() {
                if (!boardRect?.width || !boardRect?.height) {
                    return 0;
                }
                return clamp(Math.min(boardRect.width, boardRect.height) * 0.42, 150, 240);
            }

            function isOpposite(first, second) {
                return first.x + second.x === 0 && first.y + second.y === 0;
            }

            function getDirectionName(vector) {
                return Object.entries(directionVectors).find(([, candidate]) => (
                    candidate.x === vector.x && candidate.y === vector.y
                ))?.[0] || "right";
            }

            function updateDirectionControls() {
                const activeDirection = getDirectionName(queuedHeading || heading);
                const isDisabled = paused || completed;

                directionButtons.forEach((button) => {
                    const isActive = button.dataset.snakeDirection === activeDirection;
                    button.disabled = isDisabled;
                    button.classList.toggle("is-active", isActive && !isDisabled);
                    button.setAttribute("aria-pressed", isActive ? "true" : "false");
                });
            }

            function requestDirection(directionName) {
                const nextVector = directionVectors[directionName];
                if (!nextVector || paused || completed) {
                    return;
                }

                const reference = queuedHeading || heading;
                if (isOpposite(reference, nextVector)) {
                    return;
                }

                queuedHeading = { x: nextVector.x, y: nextVector.y };
                updateDirectionControls();
            }

            function boardCenter() {
                return {
                    x: (boardRect?.width || 0) / 2,
                    y: (boardRect?.height || 0) / 2,
                };
            }

            function setElementPoint(element, point) {
                element.style.transform = `translate(${point.x}px, ${point.y}px) translate(-50%, -50%)`;
            }

            function updateBoardRect(resetPosition) {
                boardRect = playfield.getBoundingClientRect();
                if (!boardRect.width || !boardRect.height) {
                    return;
                }

                const center = boardCenter();
                if (resetPosition) {
                    headPoint = { x: center.x, y: center.y };
                    heading = { x: 1, y: 0 };
                    queuedHeading = null;
                    bodyPoints.length = 0;
                    return;
                }

                headPoint = {
                    x: clamp(headPoint.x, headRadius, boardRect.width - headRadius),
                    y: clamp(headPoint.y, headRadius, boardRect.height - headRadius),
                };
                bodyPoints.forEach((point) => {
                    point.x = clamp(point.x, segmentRadius, boardRect.width - segmentRadius);
                    point.y = clamp(point.y, segmentRadius, boardRect.height - segmentRadius);
                });
            }

            function getApplePoint(apple) {
                return {
                    x: (Number.parseFloat(apple.dataset.x || "50") / 100) * boardRect.width,
                    y: (Number.parseFloat(apple.dataset.y || "50") / 100) * boardRect.height,
                };
            }

            function syncSegments() {
                const desiredCount = baseSegmentCount + answeredCount;
                while (segments.length < desiredCount) {
                    const segment = document.createElement("div");
                    segment.className = "snake-segment";
                    segmentHost.appendChild(segment);
                    segments.push(segment);
                    const anchorPoint = !bodyPoints.length
                        ? {
                            x: headPoint.x - heading.x * headSegmentDistance,
                            y: headPoint.y - heading.y * headSegmentDistance,
                        }
                        : segments.length > baseSegmentCount
                            ? bodyPoints[bodyPoints.length - 1]
                            : {
                                x: bodyPoints[bodyPoints.length - 1].x - heading.x * segmentDistance,
                                y: bodyPoints[bodyPoints.length - 1].y - heading.y * segmentDistance,
                            };
                    bodyPoints.push({ x: anchorPoint.x, y: anchorPoint.y });
                }
            }

            function solveBodyChain() {
                bodyPoints.forEach((point, index) => {
                    const previousPoint = index === 0 ? headPoint : bodyPoints[index - 1];
                    const desiredDistance = index === 0 ? headSegmentDistance : segmentDistance;
                    const direction = normalizeVector(
                        point.x - previousPoint.x,
                        point.y - previousPoint.y,
                        { x: -heading.x, y: -heading.y },
                    );

                    point.x = previousPoint.x + direction.x * desiredDistance;
                    point.y = previousPoint.y + direction.y * desiredDistance;
                    point.x = clamp(point.x, segmentRadius, boardRect.width - segmentRadius);
                    point.y = clamp(point.y, segmentRadius, boardRect.height - segmentRadius);
                });
            }

            function renderSnake() {
                setElementPoint(head, headPoint);
                segments.forEach((segment, index) => {
                    setElementPoint(segment, bodyPoints[index] || headPoint);
                });
            }

            function updateHud() {
                if (progressValue) {
                    progressValue.textContent = String(answeredCount);
                }
                if (remainingValue) {
                    remainingValue.textContent = String(Math.max(totalItems - answeredCount, 0));
                }
                if (scoreValue) {
                    scoreValue.textContent = String(localScore);
                }
            }

            function hideQuestionLayer() {
                activeItemId = "";
                paused = false;
                root.classList.remove("snake-player-paused");
                questionLayer.hidden = true;
                questionCards.forEach((card) => {
                    card.hidden = true;
                    card.classList.remove("snake-question-card-live");
                });
                if (submitState) {
                    submitState.hidden = true;
                }
                if (completeMessage) {
                    completeMessage.hidden = true;
                }
                updateDirectionControls();
            }

            function finishRun() {
                completed = true;
                paused = true;
                root.classList.add("snake-player-paused");
                questionLayer.hidden = false;
                questionCards.forEach((card) => {
                    card.hidden = true;
                    card.classList.remove("snake-question-card-live");
                });

                if (preview) {
                    if (completeMessage) {
                        completeMessage.hidden = false;
                    }
                    updateDirectionControls();
                    return;
                }

                if (submitState) {
                    submitState.hidden = false;
                }
                updateDirectionControls();
                root.classList.add("player-shell-checking");
                window.setTimeout(() => nativeSubmit.call(submitForm), 360);
            }

            function handleAnswer(card, input) {
                const itemId = card.dataset.itemId || "";
                const apple = appleMap.get(itemId);
                const correctOption = card.dataset.correctOption || "";
                const points = Number.parseInt(card.dataset.points || "0", 10) || 0;
                const delay = revealChoiceState(card, input, revealCorrect);

                if (input.value === correctOption) {
                    localScore += points;
                }

                const hiddenInput = answerTargets.get(itemId);
                if (hiddenInput) {
                    hiddenInput.value = input.value;
                }

                if (apple) {
                    apple.classList.add("snake-apple-bite");
                }

                window.setTimeout(() => {
                    answeredCount += 1;
                    syncSegments();
                    updateHud();

                    if (apple) {
                        apple.dataset.eaten = "1";
                        apple.classList.remove("snake-apple-bite");
                        apple.classList.add("snake-apple-eaten");
                    }

                    hideQuestionLayer();

                    if (answeredCount >= totalItems) {
                        finishRun();
                    }
                }, delay + 180);
            }

            function showQuestion(itemId) {
                const card = questionMap.get(itemId);
                if (!card) {
                    paused = false;
                    return;
                }

                activeItemId = itemId;
                questionLayer.hidden = false;
                root.classList.add("snake-player-paused");
                questionCards.forEach((candidate) => {
                    const isCurrent = candidate === card;
                    candidate.hidden = !isCurrent;
                    candidate.classList.toggle("snake-question-card-live", isCurrent);
                });
                if (submitState) {
                    submitState.hidden = true;
                }
                if (completeMessage) {
                    completeMessage.hidden = true;
                }

                const feedback = card.querySelector("[data-question-feedback]");
                if (feedback) {
                    feedback.hidden = true;
                    feedback.textContent = "";
                }

                card.querySelectorAll("input[type='radio']").forEach((input) => {
                    input.checked = false;
                });
                delete card.dataset.locked;
                updateDirectionControls();
            }

            function consumeApple(apple) {
                if (paused || completed || apple.dataset.eaten === "1" || apple.dataset.locked === "1") {
                    return;
                }

                apple.dataset.locked = "1";
                paused = true;
                root.classList.add("snake-player-paused");
                apple.classList.add("snake-apple-bite");
                updateDirectionControls();

                window.setTimeout(() => {
                    showQuestion(apple.dataset.itemId || "");
                }, 180);
            }

            function checkCollisions() {
                const threshold = headRadius + beaconRadius - 6;
                appleElements.some((apple) => {
                    if (apple.dataset.eaten === "1") {
                        return false;
                    }
                    return distance(headPoint, getApplePoint(apple)) <= threshold && (consumeApple(apple), true);
                });
            }

            function handleDirectionKeydown(event) {
                const directionName = directionKeys[event.key];
                if (!directionName) {
                    return;
                }

                const target = event.target;
                if (target instanceof HTMLElement && target.closest("input, textarea, select, button")) {
                    return;
                }

                event.preventDefault();
                requestDirection(directionName);
            }

            function tick(timestamp) {
                if (!boardRect?.width || !boardRect?.height) {
                    frameId = window.requestAnimationFrame(tick);
                    return;
                }

                if (!lastTimestamp) {
                    lastTimestamp = timestamp;
                }
                const delta = Math.min(timestamp - lastTimestamp, 32);
                lastTimestamp = timestamp;

                if (!paused && !completed) {
                    if (queuedHeading) {
                        heading = queuedHeading;
                        queuedHeading = null;
                        updateDirectionControls();
                    }

                    const dt = delta / 1000;
                    const previousHead = { x: headPoint.x, y: headPoint.y };
                    const speed = movementSpeed();

                    headPoint = {
                        x: clamp(headPoint.x + heading.x * speed * dt, headRadius, boardRect.width - headRadius),
                        y: clamp(headPoint.y + heading.y * speed * dt, headRadius, boardRect.height - headRadius),
                    };

                    const movement = {
                        x: headPoint.x - previousHead.x,
                        y: headPoint.y - previousHead.y,
                    };
                    if (Math.hypot(movement.x, movement.y) > 0.5) {
                        heading = normalizeVector(movement.x, movement.y, heading);
                    }

                    solveBodyChain();
                    renderSnake();
                    checkCollisions();
                } else {
                    solveBodyChain();
                    renderSnake();
                }

                frameId = window.requestAnimationFrame(tick);
            }

            questionCards.forEach((card) => {
                card.querySelectorAll("input[type='radio']").forEach((input) => {
                    input.addEventListener("change", () => {
                        if (card.dataset.locked === "1") {
                            return;
                        }

                        card.dataset.locked = "1";
                        markSelectedOption(input);
                        handleAnswer(card, input);
                    });
                });
            });

            directionButtons.forEach((button) => {
                button.addEventListener("click", () => {
                    requestDirection(button.dataset.snakeDirection || "");
                });
            });

            window.addEventListener("keydown", handleDirectionKeydown);

            window.addEventListener("resize", () => {
                updateBoardRect(false);
                renderSnake();
            });

            updateBoardRect(true);
            syncSegments();
            updateHud();
            updateDirectionControls();
            renderSnake();
            frameId = window.requestAnimationFrame(tick);
        });
    }

    function fallbackCopyText(text) {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.setAttribute("readonly", "readonly");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        textarea.style.pointerEvents = "none";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        const success = document.execCommand("copy");
        textarea.remove();
        return success;
    }

    async function copyTextToClipboard(text) {
        if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(text);
            return;
        }

        if (!fallbackCopyText(text)) {
            throw new Error("copy_failed");
        }
    }

    function initCopyLinkButtons() {
        const copyButtons = document.querySelectorAll("[data-copy-link]");
        const toast = document.querySelector("[data-copy-toast]");
        if (!copyButtons.length) {
            return;
        }

        let hideToastTimeoutId = 0;

        function showToast(message, isError = false) {
            if (!toast) {
                return;
            }

            window.clearTimeout(hideToastTimeoutId);
            toast.textContent = message;
            toast.hidden = false;
            toast.classList.add("is-visible");
            toast.classList.toggle("is-error", isError);

            hideToastTimeoutId = window.setTimeout(() => {
                toast.classList.remove("is-visible");
                window.setTimeout(() => {
                    toast.hidden = true;
                    toast.classList.remove("is-error");
                }, 180);
            }, 2200);
        }

        copyButtons.forEach((button) => {
            button.addEventListener("click", async () => {
                const link = button.dataset.copyLink;
                if (!link) {
                    return;
                }

                try {
                    await copyTextToClipboard(link);
                    showToast("\u0421\u0441\u044b\u043b\u043a\u0430 \u0441\u043a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u043d\u0430");
                } catch (error) {
                    showToast("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u0441\u044b\u043b\u043a\u0443", true);
                }
            });
        });
    }

    initQuestionBankEditors();
    initRevealStagger();
    initOptionSelection();
    initSelects();
    initDelayedSubmitForms();
    initCopyLinkButtons();
    initQuizPlayers();
    initBoxPlayers();
    initWheelPlayers();
    initMatchingPlayers();
    initCategorizePlayers();
    initSnakePlayers();
})();
