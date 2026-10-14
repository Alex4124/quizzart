(() => {
    const { wait, submitAction, applyChoiceFeedback, finishIfComplete, focusFirst } = window.QuizzartPlayer;

    function initMatchingPlayers() {
        document.querySelectorAll("[data-matching-player]").forEach((root) => {
            const questions = Array.from(root.querySelectorAll("[data-matching-question]"));
            const bank = root.querySelector("[data-matching-bank]");
            const cards = Array.from(root.querySelectorAll("[data-matching-choice]"));
            if (!questions.length || !bank || !cards.length) {
                return;
            }

            // The bank is shared by every row: its cards submit the form of the row on screen.
            function attachBank(question) {
                const form = question.querySelector("[data-answer-form]");
                const prompt = question.querySelector("h2[id]");
                cards.forEach((card) => {
                    card.classList.remove("is-selected", "is-correct", "is-wrong");
                    card.removeAttribute("aria-pressed");
                    card.setAttribute("form", form.id);
                    if (prompt) {
                        card.setAttribute("aria-describedby", prompt.id);
                    }
                    card.disabled = false;
                });
            }

            // On a phone the bank runs far below the row: bring the next prompt back from under the sticky topbar.
            function revealQuestion(question) {
                const topbar = document.querySelector(".player-topbar");
                const visibleTop = topbar ? topbar.getBoundingClientRect().bottom : 0;
                const offset = question.getBoundingClientRect().top - visibleTop - 12;
                if (offset < 0) {
                    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
                    window.scrollBy({ top: offset, behavior: reduceMotion ? "auto" : "smooth" });
                }
            }

            function showQuestion(question) {
                questions.forEach((candidate) => {
                    const isCurrent = candidate === question;
                    candidate.hidden = !isCurrent;
                    candidate.classList.toggle("matching-card-current", isCurrent);
                    candidate.classList.remove("matching-card-enter", "matching-card-exit");
                });
                attachBank(question);
                window.requestAnimationFrame(() => question.classList.add("matching-card-enter"));
                focusFirst(bank);
                revealQuestion(question);
            }

            // A copy of a bank card for the row's dock. The server names cards by their exact bank text
            // (feedback.correct_option is the card's text even when the row's answer differs in case).
            function dockCard(text, state) {
                const source = cards.find((card) => card.value === text);
                const element = document.createElement("span");
                element.className = `option-row matching-choice matching-dock-card ${state}`;
                if (source) {
                    source.childNodes.forEach((node) => element.appendChild(node.cloneNode(true)));
                } else {
                    const label = document.createElement("span");
                    label.textContent = text;
                    element.appendChild(label);
                }
                return element;
            }

            function fillDock(question, feedback) {
                const dock = question.querySelector("[data-matching-dock]");
                if (!dock) {
                    return;
                }
                const verdict = feedback.is_correct === true ? "is-correct" : feedback.is_correct === false ? "is-wrong" : "";
                const placed = [dockCard(feedback.submitted, `is-selected ${verdict}`)];
                if (feedback.is_correct === false && feedback.correct_option) {
                    placed.push(dockCard(feedback.correct_option, "is-correct"));
                }
                dock.replaceChildren(...placed);
                dock.classList.add("matching-dock-filled");
            }

            questions.forEach((question) => {
                const form = question.querySelector("[data-answer-form]");
                if (!form) {
                    return;
                }

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
                        cards,
                        chosen,
                        payload.feedback,
                        form.querySelector("[data-question-feedback]"),
                    );
                    fillDock(question, payload.feedback);
                    // The last row stays on screen with its feedback until the results open.
                    if (finishIfComplete(payload, root, delay)) {
                        return;
                    }
                    await wait(Math.max(120, delay - 300));
                    question.classList.remove("matching-card-enter");
                    question.classList.add("matching-card-exit");
                    await wait(300);

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
        initMatchingPlayers,
    ].forEach((init) => {
        try {
            init();
        } catch (error) {
            console.error(`[quizzart] ${init.name} failed`, error);
        }
    });
})();
