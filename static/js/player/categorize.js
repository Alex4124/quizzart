(() => {
    const { wait, submitAction, applyChoiceFeedback, finishIfComplete, focusFirst } = window.QuizzartPlayer;
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)");

    function initCategorizePlayers() {
        document.querySelectorAll("[data-categorize-player]").forEach((root) => {
            const board = root.querySelector("[data-categorize-board]");
            const cards = Array.from(root.querySelectorAll("[data-categorize-card]"));
            if (!board || !cards.length) {
                return;
            }
            // One card is open at a time; the others wait until it is answered.
            let activeCard = null;

            const stateOf = (card) => card.dataset.state || "closed";
            const openerOf = (card) => card.querySelector("[data-categorize-open]");
            const backOf = (card) => card.querySelector("[data-categorize-back]");

            function setBadge(card, text) {
                const badge = card.querySelector("[data-categorize-badge]");
                if (badge) {
                    badge.textContent = text;
                }
            }

            // The face turned away from the student is inert: it takes no clicks, no focus and is not read out.
            function renderBoard() {
                board.classList.toggle("cards-board-has-active", Boolean(activeCard));
                cards.forEach((card) => {
                    const state = stateOf(card);
                    const isBlocked = Boolean(activeCard) && card !== activeCard && state === "closed";
                    card.classList.toggle("cards-card-closed", state === "closed");
                    card.classList.toggle("cards-card-open", state === "open");
                    card.classList.toggle("cards-card-answered", state === "answered");
                    card.classList.toggle("cards-card-blocked", isBlocked);

                    const opener = openerOf(card);
                    if (opener) {
                        opener.inert = state !== "closed";
                        opener.disabled = state !== "closed" || isBlocked;
                    }
                    const back = backOf(card);
                    if (back) {
                        back.inert = state === "closed";
                    }
                });
            }

            function openCard(card) {
                if (activeCard || stateOf(card) !== "closed") {
                    return;
                }
                activeCard = card;
                card.dataset.state = "open";
                setBadge(card, "Открыта");
                renderBoard();
                focusFirst(backOf(card));
            }

            // After an answer the keyboard goes on to the next closed card, wrapping round the board.
            function focusNextCard(card) {
                const start = cards.indexOf(card);
                const ordered = cards.slice(start + 1).concat(cards.slice(0, start));
                const next = ordered.find((candidate) => stateOf(candidate) === "closed");
                if (next) {
                    openerOf(next)?.focus();
                }
            }

            cards.forEach((card) => {
                openerOf(card)?.addEventListener("click", () => openCard(card));

                const form = card.querySelector("[data-answer-form]");
                if (!form) {
                    return;
                }
                const options = Array.from(form.querySelectorAll("button[name='answer']"));

                form.addEventListener("submit", async (event) => {
                    const chosen = event.submitter;
                    if (!chosen || chosen.name !== "answer") {
                        return;
                    }
                    event.preventDefault();
                    if (activeCard !== card || stateOf(card) !== "open") {
                        return;
                    }

                    const payload = await submitAction(form, { root, answer: chosen.value });
                    if (!payload?.feedback) {
                        return;
                    }

                    // A card answered earlier (another tab, a double click) shows the answer the server kept.
                    const saved = options.find((option) => option.value === payload.feedback.submitted) || chosen;
                    const feedback = form.querySelector("[data-question-feedback]");
                    card.dataset.state = "answered";
                    setBadge(card, "Отвечено");
                    const delay = applyChoiceFeedback(options, saved, payload.feedback, feedback);
                    // A long card scrolls inside: the note under the options may be out of sight.
                    feedback?.scrollIntoView({ block: "nearest", behavior: reducedMotion?.matches ? "auto" : "smooth" });
                    await wait(delay);

                    activeCard = null;
                    renderBoard();
                    if (finishIfComplete(payload, root)) {
                        return;
                    }
                    if (cards.every((candidate) => stateOf(candidate) === "answered")) {
                        // The teacher added cards mid-run: the server has more than this page.
                        window.location.reload();
                        return;
                    }
                    focusNextCard(card);
                });
            });

            renderBoard();
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
