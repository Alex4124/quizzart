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

    window.QuizzartPlayer = {
        nativeSubmit,
        markSelectedOption,
        preserveSubmittedValue,
        revealChoiceState,
        enhanceAnswerForm,
        submitFormAsJson,
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
