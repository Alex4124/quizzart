// Shared player helpers; each template's script reads them from window.QuizzartPlayer.
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

    // ---- Answers checked on the server -------------------------------------------------------------
    // A player root carries data-player-root, data-action-url (play page, or the teacher's preview
    // endpoint), data-preview="1|0" and data-total-count. Every answer is a form with action, item_key
    // and answer; the server replies with feedback, never with the answer key.

    const CHECKING_CLASS = "player-shell-checking";
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)");

    class ActionError extends Error {
        constructor(kind, message, payload = null) {
            super(message);
            this.kind = kind;
            this.payload = payload;
        }
    }

    function wait(milliseconds) {
        const duration = reducedMotion?.matches ? Math.min(milliseconds, 150) : milliseconds;
        return new Promise((resolve) => window.setTimeout(resolve, duration));
    }

    async function postAction(url, formData) {
        let response;
        try {
            response = await fetch(url, {
                method: "POST",
                body: formData,
                headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
                credentials: "same-origin",
            });
        } catch (error) {
            throw new ActionError("network", "Нет связи с сервером. Проверьте интернет.");
        }

        let payload = null;
        try {
            payload = await response.json();
        } catch (error) {
            throw new ActionError("unexpected", "Сервер ответил неожиданно. Обновите страницу.");
        }
        if (response.ok && payload?.ok) {
            return payload;
        }
        if (response.status === 409) {
            throw new ActionError("session", payload?.error || "Прохождение не найдено.", payload);
        }
        if (response.status === 400) {
            throw new ActionError("validation", payload?.error || "Ответ не принят.", payload);
        }
        throw new ActionError("unexpected", payload?.error || "Не удалось сохранить ответ.", payload);
    }

    function playerRoot(element) {
        return element.closest("[data-player-root]");
    }

    function isPreview(root) {
        return root?.dataset.preview === "1";
    }

    // The teacher's preview saves nothing, so its progress lives in the page.
    const previewStates = new WeakMap();

    function previewState(root) {
        if (!previewStates.has(root)) {
            previewStates.set(root, { answered: new Set(), score: 0, hidesScore: false });
        }
        return previewStates.get(root);
    }

    function previewAnsweredKeys(root) {
        return Array.from(previewState(root).answered);
    }

    function applyPreviewProgress(root, payload) {
        const state = previewState(root);
        if (payload.feedback && payload.item_key && !state.answered.has(payload.item_key)) {
            state.answered.add(payload.item_key);
            if (payload.feedback.score_awarded === null) {
                state.hidesScore = true;
            }
            state.score += payload.feedback.score_awarded || 0;
        }
        const total = Number.parseInt(root.dataset.totalCount || "0", 10) || 0;
        Object.assign(payload, {
            answered_count: state.answered.size,
            total_count: total,
            score: state.hidesScore ? null : state.score,
            is_complete: total > 0 && state.answered.size >= total,
            redirect_url: null,
        });
        return payload;
    }

    function shellValue(selector) {
        return document.querySelector(selector);
    }

    function updateShell(payload) {
        const total = Number(payload.total_count) || 0;
        const answered = Math.min(Number(payload.answered_count) || 0, total);
        const percent = total ? Math.round((answered / total) * 100) : 0;
        const score = shellValue('[data-player-summary-value="score"]');
        if (score && "score" in payload) {
            score.textContent = payload.score === null ? "—" : String(payload.score);
        }
        const progress = shellValue('[data-player-summary-value="progress"]');
        if (progress) {
            progress.textContent = `${percent}%`;
        }
        const answeredFact = shellValue('[data-player-fact-value="answered"]');
        if (answeredFact) {
            answeredFact.textContent = total ? `${answered} из ${total}` : "0";
        }
        const remainingFact = shellValue('[data-player-fact-value="remaining"]');
        if (remainingFact) {
            remainingFact.textContent = String(Math.max(total - answered, 0));
        }
        const heading = shellValue("[data-player-progress-heading]");
        if (heading) {
            heading.textContent = `${percent}% готово`;
        }
        const ring = shellValue("[data-player-progress-ring]");
        if (ring) {
            ring.style.setProperty("--progress", String(percent));
        }
        const ringLabel = shellValue("[data-player-progress-ring-label]");
        if (ringLabel) {
            ringLabel.textContent = `${percent}%`;
        }
        const bar = shellValue("[data-player-progress-bar-fill]");
        if (bar) {
            bar.style.width = `${percent}%`;
        }
        const segments = Array.from(document.querySelectorAll("[data-player-progress-segment]"));
        const filled = Math.max(0, Math.min(segments.length, Math.round(percent / 20)));
        segments.forEach((segment, index) => segment.classList.toggle("is-filled", index < filled));
    }

    function feedbackElementFor(form) {
        return form.querySelector("[data-question-feedback]") || form.closest("[data-item-id]")?.querySelector("[data-question-feedback]");
    }

    function showFormError(form, message) {
        const element = feedbackElementFor(form);
        if (!element) {
            return;
        }
        element.textContent = message;
        element.classList.add("is-error");
        element.hidden = false;
    }

    function fallbackSubmit(form, formData) {
        // Without a usable JSON reply the page posts normally; the server then renders the run from saved answers.
        form.querySelectorAll("input[data-fallback-field]").forEach((input) => input.remove());
        formData.forEach((value, name) => {
            if (
                name === "answer" ||
                name === "csrfmiddlewaretoken" ||
                form.querySelector(`[name="${CSS.escape(name)}"]:not(button)`)
            ) {
                return;
            }
            const input = document.createElement("input");
            input.type = "hidden";
            input.name = name;
            input.value = String(value);
            input.dataset.fallbackField = "1";
            form.appendChild(input);
        });
        const answer = formData.get("answer");
        if (answer !== null) {
            let answerInput = form.querySelector("input[data-fallback-answer]");
            if (!answerInput) {
                answerInput = document.createElement("input");
                answerInput.type = "hidden";
                answerInput.name = "answer";
                answerInput.dataset.fallbackAnswer = "1";
                form.appendChild(answerInput);
            }
            answerInput.value = String(answer);
        }
        nativeSubmit.call(form);
    }

    // Sends one form to the server. Resolves with the JSON reply, or null when the reply was an error that
    // is already shown (validation), a redirect (session gone) or a fallback to a normal form post.
    async function submitAction(form, { root = playerRoot(form), answer, fields = {} } = {}) {
        if (!root || form.dataset.pending === "1") {
            return null;
        }
        form.dataset.pending = "1";
        const formData = new FormData(form);
        if (answer !== undefined) {
            formData.set("answer", answer);
        }
        Object.entries(fields).forEach(([name, value]) => formData.set(name, value));

        const feedback = feedbackElementFor(form);
        if (feedback?.classList.contains("is-error")) {
            feedback.hidden = true;
            feedback.classList.remove("is-error");
        }
        root.classList.add(CHECKING_CLASS);
        try {
            const payload = await postAction(root.dataset.actionUrl || form.action || window.location.href, formData);
            if (isPreview(root)) {
                applyPreviewProgress(root, payload);
            }
            updateShell(payload);
            return payload;
        } catch (error) {
            if (error.kind === "session" && error.payload?.redirect_url) {
                window.location.assign(error.payload.redirect_url);
                return null;
            }
            if (error.kind === "validation" || isPreview(root)) {
                showFormError(form, error.message);
                return null;
            }
            fallbackSubmit(form, formData);
            return null;
        } finally {
            delete form.dataset.pending;
            root.classList.remove(CHECKING_CLASS);
        }
    }

    function feedbackText(feedback) {
        if (feedback?.is_correct === true) {
            return "Верно. Ответ засчитан.";
        }
        if (feedback?.is_correct === false) {
            return feedback.correct_option ? `Неверно. Правильный ответ: ${feedback.correct_option}` : "Неверно.";
        }
        return "Ответ сохранён.";
    }

    // Longer pause when there is a correct answer to read.
    function feedbackDelay(feedback) {
        return feedback?.is_correct === false && feedback.correct_option ? 1400 : 650;
    }

    function controlValue(control) {
        return control.dataset.choiceValue ?? control.value ?? "";
    }

    // Marks the chosen control and, when the server revealed it, the correct one; locks every control.
    function applyChoiceFeedback(controls, chosen, feedback, feedbackElement = null) {
        const correctText = feedback?.correct_option ?? null;
        controls.forEach((control) => {
            const isChosen = control === chosen || controlValue(control) === feedback?.submitted;
            control.classList.toggle("is-selected", isChosen);
            control.classList.toggle(
                "is-correct",
                (isChosen && feedback?.is_correct === true) || (correctText !== null && controlValue(control) === correctText),
            );
            control.classList.toggle("is-wrong", isChosen && feedback?.is_correct === false);
            control.setAttribute("aria-pressed", isChosen ? "true" : "false");
            control.disabled = true;
        });
        if (feedbackElement) {
            feedbackElement.classList.remove("is-error");
            feedbackElement.textContent = feedbackText(feedback);
            feedbackElement.hidden = false;
        }
        return feedbackDelay(feedback);
    }

    // True when the run is over: students go to their results, the teacher's preview shows a note.
    function finishIfComplete(payload, root, delay = 0) {
        if (!payload?.is_complete) {
            return false;
        }
        if (isPreview(root)) {
            const note = root.querySelector("[data-preview-complete]") || document.querySelector("[data-preview-complete]");
            if (note) {
                note.hidden = false;
            }
            return true;
        }
        if (payload.redirect_url) {
            root.classList.add(CHECKING_CLASS);
            window.setTimeout(() => window.location.assign(payload.redirect_url), delay);
        }
        return true;
    }

    function focusFirst(scope) {
        const target = scope?.querySelector("button:not([disabled]), input:not([disabled]):not([type='hidden'])");
        if (target) {
            target.focus({ preventScroll: true });
        }
    }

    window.QuizzartPlayer = {
        nativeSubmit,
        markSelectedOption,
        preserveSubmittedValue,
        revealChoiceState,
        enhanceAnswerForm,
        submitFormAsJson,
        wait,
        postAction,
        playerRoot,
        isPreview,
        previewAnsweredKeys,
        updateShell,
        showFormError,
        submitAction,
        feedbackText,
        feedbackDelay,
        applyChoiceFeedback,
        finishIfComplete,
        focusFirst,
    };

    // One broken widget must not stop the rest of the page from initialising.
    [
        initRevealStagger,
        initOptionSelection,
    ].forEach((init) => {
        try {
            init();
        } catch (error) {
            console.error(`[quizzart] ${init.name} failed`, error);
        }
    });
})();
