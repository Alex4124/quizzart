(() => {
    const MAX_POINTS = 1000;
    const UNDO_TIMEOUT_MS = 6000;
    // Radio group names start with this prefix; editor.js leaves such fields out of its unsaved-changes check.
    const RADIO_NAME_PREFIX = "qb-correct-";
    let uniqueCounter = 0;

    function uniqueId(prefix) {
        uniqueCounter += 1;
        return `${prefix}-${uniqueCounter}`;
    }

    // `parseInt(...) || fallback` would turn a deliberate 0 points into the default.
    function parsePoints(rawValue, fallback) {
        const parsed = Number.parseInt(String(rawValue ?? ""), 10);
        return Number.isNaN(parsed) ? fallback : parsed;
    }

    // normalize_answer() in interactive_templates/utils.py: answers are compared without case and extra spaces.
    function normalizeAnswer(value) {
        return value.toLowerCase().trim().split(/\s+/).filter(Boolean).join(" ");
    }

    function normalizeOptions(options) {
        return Array.isArray(options)
            ? options.map((option) => ({
                text: typeof option?.text === "string" ? option.text : "",
                is_correct: Boolean(option?.is_correct),
            }))
            : [];
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
                id: typeof item?.id === "string" ? item.id : "",
                prompt: typeof item?.prompt === "string" ? item.prompt : "",
                points: parsePoints(item?.points, defaultPoints),
                options: normalizeOptions(item?.options),
            }));
        } catch (error) {
            return [];
        }
    }

    // The rules of parse_question_bank_text() (interactive_templates/utils.py), with the same wording.
    // Lines are numbered as the teacher sees them in the textarea, blank lines included.
    function parseBulkText(rawText, defaultPoints) {
        const items = [];
        const errors = [];

        rawText.split(/\r\n|\r|\n/).forEach((rawLine, lineIndex) => {
            const line = rawLine.trim();
            if (!line) {
                return;
            }
            const number = lineIndex + 1;
            const fail = (message) => errors.push({ line: number, message });

            const parts = line.split("|").map((part) => part.trim()).filter(Boolean);
            if (parts.length < 3) {
                fail(`Строка ${number} должна содержать вопрос и минимум два варианта ответа.`);
                return;
            }

            const prompt = parts[0];
            let optionParts = parts.slice(1);
            let points = defaultPoints;
            // ASCII digits only, like the server: "²" stays an answer option.
            if (/^-?[0-9]+$/.test(optionParts[optionParts.length - 1])) {
                points = Number.parseInt(optionParts[optionParts.length - 1], 10);
                if (!(points >= 0 && points <= MAX_POINTS)) {
                    fail(`Строка ${number}: баллы должны быть от 0 до ${MAX_POINTS}.`);
                    return;
                }
                optionParts = optionParts.slice(0, -1);
            }

            if (optionParts.length < 2) {
                fail(`В строке ${number} после баллов должно остаться минимум два варианта.`);
                return;
            }

            const options = [];
            for (const rawOption of optionParts) {
                const isCorrect = rawOption.startsWith("*");
                const text = isCorrect ? rawOption.slice(1).trim() : rawOption;
                if (!text) {
                    fail(`В строке ${number} найден пустой вариант ответа.`);
                    return;
                }
                options.push({ text, is_correct: isCorrect });
            }

            if (options.filter((option) => option.is_correct).length !== 1) {
                fail(`В строке ${number} должен быть ровно один правильный ответ, помеченный *.`);
                return;
            }

            const seen = new Set();
            for (const option of options) {
                const key = normalizeAnswer(option.text);
                if (seen.has(key)) {
                    fail(`Строка ${number}: варианты ответа не должны повторяться («${option.text}»).`);
                    return;
                }
                seen.add(key);
            }

            // A pasted question is new: the server gives it an id on save.
            items.push({ id: "", prompt, points, options });
        });

        return { items, errors };
    }

    function initQuestionBankEditors() {
        document.querySelectorAll("[data-question-bank-editor]").forEach((root) => {
            const form = root.closest("form");
            const questionList = root.querySelector("[data-question-bank-list]");
            const questionTemplate = root.querySelector("[data-question-template]");
            const answerTemplate = root.querySelector("[data-answer-template]");
            const addQuestionButton = root.querySelector("[data-add-question]");
            const statusRegion = root.querySelector("[data-question-bank-status]");
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

            const toast = createToast();

            function questionCards() {
                return Array.from(questionList.querySelectorAll("[data-question-card]"));
            }

            function answerCards(questionCard) {
                return Array.from(questionCard.querySelectorAll("[data-answer-card]"));
            }

            function announce(message) {
                if (!statusRegion) {
                    return;
                }
                // Re-setting the same text would not be read again.
                statusRegion.textContent = "";
                window.setTimeout(() => {
                    statusRegion.textContent = message;
                }, 30);
            }

            function createEmptyQuestion() {
                // The server assigns ids to new questions on save.
                return {
                    id: "",
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

            function readQuestion(questionCard) {
                return {
                    id: questionCard.dataset.itemId || "",
                    prompt: questionCard.querySelector("[data-question-prompt]")?.value || "",
                    points: parsePoints(questionCard.querySelector("[data-question-points]")?.value, defaultPoints),
                    options: answerCards(questionCard).map((answerCard) => ({
                        text: answerCard.querySelector("[data-answer-text]")?.value || "",
                        is_correct: Boolean(answerCard.querySelector("[data-answer-correct]")?.checked),
                    })),
                };
            }

            function serializeItems() {
                itemsJsonInput.value = JSON.stringify(questionCards().map(readQuestion));
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

            // Titles, accessible names and which buttons apply, after every change of the list.
            function refreshQuestionLabels() {
                const cards = questionCards();
                cards.forEach((questionCard, questionIndex) => {
                    const number = questionIndex + 1;
                    const title = questionCard.querySelector("[data-question-title]");
                    if (title) {
                        title.textContent = `Вопрос ${number}`;
                    }

                    const moveUp = questionCard.querySelector("[data-move-question='up']");
                    const moveDown = questionCard.querySelector("[data-move-question='down']");
                    const duplicate = questionCard.querySelector("[data-duplicate-question]");
                    const remove = questionCard.querySelector("[data-remove-question]");
                    if (moveUp) {
                        moveUp.disabled = questionIndex === 0;
                        moveUp.setAttribute("aria-label", `Переместить вопрос ${number} вверх`);
                        moveUp.title = "Переместить вверх";
                    }
                    if (moveDown) {
                        moveDown.disabled = questionIndex === cards.length - 1;
                        moveDown.setAttribute("aria-label", `Переместить вопрос ${number} вниз`);
                        moveDown.title = "Переместить вниз";
                    }
                    duplicate?.setAttribute("aria-label", `Дублировать вопрос ${number}`);
                    if (remove) {
                        remove.setAttribute("aria-label", `Удалить вопрос ${number}`);
                        // aria-disabled, not disabled: still focusable, so a click can say why nothing happens.
                        if (cards.length <= 1) {
                            remove.setAttribute("aria-disabled", "true");
                            remove.title = "В интерактиве должен остаться хотя бы один вопрос";
                        } else {
                            remove.removeAttribute("aria-disabled");
                            remove.removeAttribute("title");
                        }
                    }

                    const answers = answerCards(questionCard);
                    answers.forEach((answerCard, answerIndex) => {
                        const answerTitle = answerCard.querySelector("[data-answer-title]");
                        const removeButton = answerCard.querySelector("[data-remove-answer]");
                        if (answerTitle) {
                            answerTitle.textContent = `Ответ ${answerIndex + 1}`;
                        }
                        if (removeButton) {
                            removeButton.hidden = answers.length <= 2;
                            removeButton.setAttribute("aria-label", `Удалить ответ ${answerIndex + 1} из вопроса ${number}`);
                        }
                    });
                });
            }

            function afterStructureChange() {
                refreshQuestionLabels();
                syncScoringVisibility();
                serializeItems();
            }

            function buildAnswer(questionCard, answerData) {
                const fragment = answerTemplate.content.cloneNode(true);
                const answerCard = fragment.querySelector("[data-answer-card]");
                const title = fragment.querySelector("[data-answer-title]");
                const textInput = fragment.querySelector("[data-answer-text]");
                const correctInput = fragment.querySelector("[data-answer-correct]");
                const correctLabel = fragment.querySelector("[data-answer-correct-label]");
                if (!answerCard || !title || !textInput || !correctInput) {
                    return null;
                }

                const textId = uniqueId("qb-answer");
                textInput.id = textId;
                title.htmlFor = textId;
                title.id = `${textId}-title`;
                correctInput.name = questionCard.dataset.radioName;
                correctInput.value = textId;
                if (correctLabel) {
                    // Read as «Ответ 2 Верный ответ».
                    correctLabel.id = `${textId}-correct`;
                    correctInput.setAttribute("aria-labelledby", `${title.id} ${correctLabel.id}`);
                }

                textInput.value = answerData.text || "";
                correctInput.checked = Boolean(answerData.is_correct);
                return answerCard;
            }

            function appendAnswer(questionCard, answerData) {
                const answerList = questionCard.querySelector("[data-answer-list]");
                const answerCard = answerList ? buildAnswer(questionCard, answerData) : null;
                if (answerCard) {
                    answerList.appendChild(answerCard);
                }
                return answerCard;
            }

            function buildQuestion(questionData) {
                const options = normalizeOptions(questionData?.options);
                while (options.length < 2) {
                    options.push(createEmptyAnswer());
                }
                // One radio per question: exactly one answer is marked, the first one when the data has none.
                const correctIndex = Math.max(0, options.findIndex((option) => option.is_correct));
                options.forEach((option, index) => {
                    option.is_correct = index === correctIndex;
                });

                const fragment = questionTemplate.content.cloneNode(true);
                const questionCard = fragment.querySelector("[data-question-card]");
                const title = fragment.querySelector("[data-question-title]");
                const promptInput = fragment.querySelector("[data-question-prompt]");
                const pointsInput = fragment.querySelector("[data-question-points]");
                if (!questionCard || !promptInput || !pointsInput) {
                    return null;
                }

                const questionId = uniqueId("qb-question");
                questionCard.dataset.itemId = typeof questionData?.id === "string" ? questionData.id : "";
                questionCard.dataset.radioName = `${RADIO_NAME_PREFIX}${questionId}`;
                if (title) {
                    title.id = `${questionId}-title`;
                    questionCard.setAttribute("aria-labelledby", title.id);
                }
                promptInput.value = questionData?.prompt || "";
                pointsInput.value = String(parsePoints(questionData?.points, defaultPoints));
                options.forEach((option) => appendAnswer(questionCard, option));
                return questionCard;
            }

            function insertQuestion(questionData, beforeNode = null) {
                const questionCard = buildQuestion(questionData);
                if (questionCard) {
                    questionList.insertBefore(questionCard, beforeNode);
                }
                return questionCard;
            }

            function focusTitle(questionCard) {
                const title = questionCard?.querySelector("[data-question-title]");
                if (title) {
                    questionCard.scrollIntoView({ block: "nearest" });
                    title.focus({ preventScroll: true });
                }
            }

            // ---- Problems of one card: the server's messages plus the fields they point at.

            // Mirrors parse_question_bank_editor_json(): which fields of this card the server would complain about.
            function invalidFields(questionCard) {
                const prompt = questionCard.querySelector("[data-question-prompt]");
                const pointsField = questionCard.querySelector(".question-editor-points");
                const pointsInput = questionCard.querySelector("[data-question-points]");
                const textInputs = Array.from(questionCard.querySelectorAll("[data-answer-text]"));
                const filled = textInputs.filter((input) => input.value.trim());
                const promptEmpty = !prompt?.value.trim();
                const invalid = new Set();

                if (promptEmpty && !filled.length) {
                    // An empty card is skipped on save.
                    return [];
                }
                if (promptEmpty && prompt) {
                    invalid.add(prompt);
                }
                if (filled.length < 2) {
                    textInputs.filter((input) => !input.value.trim()).forEach((input) => invalid.add(input));
                }
                const checked = questionCard.querySelector("[data-answer-correct]:checked");
                const checkedText = checked?.closest("[data-answer-card]")?.querySelector("[data-answer-text]");
                if (filled.length && checkedText && !checkedText.value.trim()) {
                    invalid.add(checkedText);
                }
                const seen = new Set();
                filled.forEach((input) => {
                    const key = normalizeAnswer(input.value);
                    if (seen.has(key)) {
                        invalid.add(input);
                    }
                    seen.add(key);
                });
                if (pointsInput && !pointsField?.hidden) {
                    const points = parsePoints(pointsInput.value, defaultPoints);
                    if (points < 0 || points > MAX_POINTS) {
                        invalid.add(pointsInput);
                    }
                }

                return Array.from(questionCard.querySelectorAll("textarea, input")).filter((field) => invalid.has(field));
            }

            function markInvalidFields(questionCard) {
                const errorList = questionCard.querySelector("[data-question-errors]");
                const fields = invalidFields(questionCard);
                questionCard.querySelectorAll("[aria-invalid]").forEach((field) => {
                    field.removeAttribute("aria-invalid");
                    field.removeAttribute("aria-describedby");
                });
                fields.forEach((field) => {
                    field.setAttribute("aria-invalid", "true");
                    if (errorList?.id) {
                        field.setAttribute("aria-describedby", errorList.id);
                    }
                });
                return fields;
            }

            function showCardErrors(questionCard, messages) {
                const errorList = questionCard.querySelector("[data-question-errors]");
                if (!errorList) {
                    return [];
                }
                errorList.id = errorList.id || uniqueId("qb-errors");
                errorList.replaceChildren(
                    ...messages.map((message) => {
                        const item = document.createElement("li");
                        item.textContent = message;
                        return item;
                    }),
                );
                errorList.hidden = false;
                questionCard.classList.add("is-invalid");
                return markInvalidFields(questionCard);
            }

            function clearCardErrors(questionCard) {
                const errorList = questionCard.querySelector("[data-question-errors]");
                if (errorList) {
                    errorList.hidden = true;
                    errorList.replaceChildren();
                }
                questionCard.classList.remove("is-invalid");
                questionCard.querySelectorAll("[aria-invalid]").forEach((field) => {
                    field.removeAttribute("aria-invalid");
                    field.removeAttribute("aria-describedby");
                });
            }

            // While the teacher fixes a marked card, its marks follow the fields; a fixed card loses them.
            function recheckCard(questionCard) {
                if (!questionCard?.classList.contains("is-invalid")) {
                    return;
                }
                if (!markInvalidFields(questionCard).length) {
                    clearCardErrors(questionCard);
                }
            }

            function showServerErrors() {
                const source = document.getElementById("question-bank-errors");
                if (!source) {
                    return;
                }
                let errors = {};
                try {
                    errors = JSON.parse(source.textContent || "{}") || {};
                } catch (error) {
                    return;
                }

                const cards = questionCards();
                let firstCard = null;
                let firstField = null;
                Object.keys(errors)
                    .map(Number)
                    .sort((a, b) => a - b)
                    .forEach((number) => {
                        const questionCard = cards[number - 1];
                        const messages = errors[String(number)];
                        if (!questionCard || !Array.isArray(messages) || !messages.length) {
                            return;
                        }
                        const fields = showCardErrors(questionCard, messages);
                        if (!firstCard) {
                            firstCard = questionCard;
                            firstField = fields[0] || questionCard.querySelector("[data-question-prompt]");
                        }
                    });

                // Only when the bank is on screen: title errors open the «Общие настройки» tab instead.
                if (firstCard && firstCard.getClientRects().length) {
                    // The header is sticky: html { scroll-padding-top } keeps the card below it.
                    firstCard.scrollIntoView({ block: "start" });
                    firstField?.focus({ preventScroll: true });
                }
            }

            // ---- Toast: one at a time, «Отменить» for the last deleted question.

            function createToast() {
                const element = document.querySelector("[data-bank-toast]");
                const text = element?.querySelector("[data-bank-toast-text]");
                const undoButton = element?.querySelector("[data-bank-toast-undo]");
                let timeoutId = 0;
                let onUndo = null;
                let onExpire = null;
                let movingFocusIn = false;

                function hide() {
                    window.clearTimeout(timeoutId);
                    if (!element || element.hidden) {
                        return;
                    }
                    const hadFocus = element.contains(document.activeElement);
                    element.classList.remove("is-visible");
                    element.hidden = true;
                    const expire = onExpire;
                    onUndo = null;
                    onExpire = null;
                    expire?.(hadFocus);
                }

                function schedule() {
                    window.clearTimeout(timeoutId);
                    timeoutId = window.setTimeout(hide, UNDO_TIMEOUT_MS);
                }

                function show(message, options = {}) {
                    if (!element || !text) {
                        return;
                    }
                    // A new toast ends the previous one (its deletion becomes final).
                    hide();
                    text.textContent = message;
                    onUndo = options.onUndo || null;
                    onExpire = options.onExpire || null;
                    if (undoButton) {
                        undoButton.hidden = !onUndo;
                    }
                    element.hidden = false;
                    window.requestAnimationFrame(() => element.classList.add("is-visible"));
                    schedule();
                    if (onUndo && options.focusUndo && undoButton) {
                        // Keyboard users land on «Отменить»; this focus alone does not stop the countdown.
                        movingFocusIn = true;
                        undoButton.focus();
                        movingFocusIn = false;
                    }
                }

                if (element) {
                    // More time when wanted: the toast waits while it is pointed at or focused by the teacher.
                    element.addEventListener("pointerenter", () => window.clearTimeout(timeoutId));
                    element.addEventListener("pointerleave", () => {
                        if (!element.contains(document.activeElement)) {
                            schedule();
                        }
                    });
                    element.addEventListener("focusin", () => {
                        if (!movingFocusIn) {
                            window.clearTimeout(timeoutId);
                        }
                    });
                    element.addEventListener("focusout", (event) => {
                        if (!element.contains(event.relatedTarget) && !element.hidden) {
                            schedule();
                        }
                    });
                    element.addEventListener("keydown", (event) => {
                        if (event.key === "Escape") {
                            hide();
                        }
                    });
                    undoButton?.addEventListener("click", () => {
                        const undo = onUndo;
                        onExpire = null;
                        hide();
                        undo?.();
                    });
                }

                return { show, hide };
            }

            // ---- Question actions

            function moveQuestion(questionCard, direction, button) {
                const cards = questionCards();
                const index = cards.indexOf(questionCard);
                const target = index + direction;
                if (index < 0 || target < 0 || target >= cards.length) {
                    return;
                }
                questionList.insertBefore(questionCard, direction < 0 ? cards[target] : cards[target].nextSibling);
                afterStructureChange();

                // Moving the node drops the focus; at the edge of the list the other arrow takes it.
                const other = questionCard.querySelector(`[data-move-question='${direction < 0 ? "down" : "up"}']`);
                (button.disabled ? other : button)?.focus({ preventScroll: true });
                questionCard.scrollIntoView({ block: "nearest" });
                announce(`Вопрос перемещён, теперь это вопрос ${target + 1}.`);
            }

            function duplicateQuestion(questionCard) {
                // A copy is a new question: no id, the server gives it one on save.
                const copy = insertQuestion({ ...readQuestion(questionCard), id: "" }, questionCard.nextSibling);
                afterStructureChange();
                if (copy) {
                    const number = questionCards().indexOf(copy) + 1;
                    copy.scrollIntoView({ block: "nearest" });
                    copy.querySelector("[data-question-prompt]")?.focus({ preventScroll: true });
                    announce(`Копия добавлена: вопрос ${number}.`);
                }
            }

            function removeQuestion(questionCard, button) {
                const cards = questionCards();
                if (cards.length <= 1) {
                    toast.show("В интерактиве должен остаться хотя бы один вопрос — последний удалить нельзя.");
                    button?.focus();
                    return;
                }

                const index = cards.indexOf(questionCard);
                const number = index + 1;
                questionCard.remove();
                afterStructureChange();

                toast.show(`Вопрос ${number} удалён.`, {
                    focusUndo: true,
                    onUndo: () => {
                        // The same node comes back: its id, answers and marks are untouched.
                        const remaining = questionCards();
                        questionList.insertBefore(questionCard, remaining[index] || null);
                        afterStructureChange();
                        focusTitle(questionCard);
                        announce(`Вопрос ${number} восстановлен.`);
                    },
                    onExpire: (hadFocus) => {
                        if (hadFocus) {
                            const remaining = questionCards();
                            focusTitle(remaining[Math.min(index, remaining.length - 1)]);
                        }
                    },
                });
            }

            function addAnswer(questionCard) {
                const answerCard = appendAnswer(questionCard, createEmptyAnswer());
                afterStructureChange();
                recheckCard(questionCard);
                answerCard?.querySelector("[data-answer-text]")?.focus();
            }

            function removeAnswer(answerCard) {
                const questionCard = answerCard.closest("[data-question-card]");
                const answers = answerCards(questionCard);
                if (answers.length <= 2) {
                    return;
                }
                const index = answers.indexOf(answerCard);
                const wasCorrect = Boolean(answerCard.querySelector("[data-answer-correct]")?.checked);
                answerCard.remove();

                const remaining = answerCards(questionCard);
                if (wasCorrect) {
                    // There is always exactly one correct answer: the first remaining one takes over.
                    const firstRadio = remaining[0]?.querySelector("[data-answer-correct]");
                    if (firstRadio) {
                        firstRadio.checked = true;
                    }
                }
                afterStructureChange();
                recheckCard(questionCard);
                const next = remaining[Math.min(index, remaining.length - 1)];
                next?.querySelector("[data-answer-text]")?.focus();
                announce(wasCorrect ? "Ответ удалён. Верным стал ответ 1." : "Ответ удалён.");
            }

            questionList.addEventListener("input", (event) => {
                serializeItems();
                recheckCard(event.target.closest("[data-question-card]"));
            });

            questionList.addEventListener("change", (event) => {
                if (event.target.matches("[data-answer-correct]")) {
                    serializeItems();
                    recheckCard(event.target.closest("[data-question-card]"));
                }
            });

            questionList.addEventListener("click", (event) => {
                const button = event.target.closest("button");
                if (!button || !questionList.contains(button) || button.disabled) {
                    return;
                }
                const questionCard = button.closest("[data-question-card]");
                if (!questionCard) {
                    return;
                }
                if (button.matches("[data-move-question]")) {
                    moveQuestion(questionCard, button.dataset.moveQuestion === "up" ? -1 : 1, button);
                } else if (button.matches("[data-duplicate-question]")) {
                    duplicateQuestion(questionCard);
                } else if (button.matches("[data-remove-question]")) {
                    removeQuestion(questionCard, button);
                } else if (button.matches("[data-add-answer]")) {
                    addAnswer(questionCard);
                } else if (button.matches("[data-remove-answer]")) {
                    removeAnswer(button.closest("[data-answer-card]"));
                }
            });

            // ---- «Вставить списком»

            function isBlankQuestion(questionCard) {
                const question = readQuestion(questionCard);
                return !question.prompt.trim() && question.options.every((option) => !option.text.trim());
            }

            function initBulkImport() {
                const opener = root.querySelector("[data-bulk-open]");
                const dialog = root.querySelector("[data-bulk-dialog]");
                const textArea = dialog?.querySelector("[data-bulk-text]");
                const errorBox = dialog?.querySelector("[data-bulk-errors]");
                const errorList = dialog?.querySelector("[data-bulk-error-list]");
                const submitButton = dialog?.querySelector("[data-bulk-submit]");
                if (!opener || !dialog || !textArea || !errorBox || !errorList || !submitButton) {
                    return;
                }
                if (typeof dialog.showModal !== "function") {
                    opener.hidden = true;
                    return;
                }

                let focusAfterClose = null;

                function showErrors(errors) {
                    errorList.replaceChildren(
                        ...errors.map((error) => {
                            const item = document.createElement("li");
                            item.textContent = error.message;
                            return item;
                        }),
                    );
                    errorBox.hidden = !errors.length;
                    if (errors.length) {
                        textArea.setAttribute("aria-invalid", "true");
                        textArea.setAttribute("aria-describedby", "bulk-import-hint bulk-import-errors");
                    } else {
                        textArea.removeAttribute("aria-invalid");
                        textArea.removeAttribute("aria-describedby");
                    }
                }

                opener.addEventListener("click", () => {
                    focusAfterClose = null;
                    dialog.showModal();
                    textArea.focus();
                });

                dialog.querySelectorAll("[data-bulk-cancel]").forEach((button) => {
                    button.addEventListener("click", () => dialog.close());
                });

                // Esc closes the dialog natively; focus goes back to the button (or to the first added question).
                dialog.addEventListener("close", () => {
                    const target = focusAfterClose;
                    focusAfterClose = null;
                    if (target) {
                        focusTitle(target);
                    } else {
                        opener.focus();
                    }
                });

                submitButton.addEventListener("click", () => {
                    const { items, errors } = parseBulkText(textArea.value, defaultPoints);
                    if (errors.length) {
                        showErrors(errors);
                        textArea.focus();
                        return;
                    }
                    showErrors([]);
                    if (!items.length) {
                        dialog.close();
                        return;
                    }

                    // An untouched empty card would only sit before the pasted questions (and is skipped on save).
                    questionCards().filter(isBlankQuestion).forEach((questionCard) => questionCard.remove());
                    const added = items.map((item) => insertQuestion(item)).filter(Boolean);
                    afterStructureChange();

                    textArea.value = "";
                    focusAfterClose = added[0] || null;
                    dialog.close();
                    toast.show(`Добавлено вопросов: ${added.length}.`);
                });
            }

            // ---- Start

            const initialItems = parseQuestionBankItems(itemsJsonInput.value, defaultPoints);
            (initialItems.length ? initialItems : [createEmptyQuestion()]).forEach((item) => insertQuestion(item));
            afterStructureChange();

            addQuestionButton.addEventListener("click", () => {
                const questionCard = insertQuestion(createEmptyQuestion());
                afterStructureChange();
                if (questionCard) {
                    questionCard.scrollIntoView({ block: "nearest" });
                    questionCard.querySelector("[data-question-prompt]")?.focus({ preventScroll: true });
                }
            });

            disableScoringInput?.addEventListener("change", syncScoringVisibility);

            initBulkImport();
            showServerErrors();

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
