(() => {
    const { wait, submitAction, applyChoiceFeedback, finishIfComplete, focusFirst, isPreview } = window.QuizzartPlayer;

    // The lid animation (playerBoxCoverCollapse in player.css); the server stores the open box meanwhile.
    const OPEN_ANIMATION_MS = 280;
    const STATES = ["unopened", "opened", "answered"];
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)");

    function initBoxPlayers() {
        document.querySelectorAll("[data-box-player]").forEach((root) => {
            const preview = isPreview(root);
            const cards = Array.from(root.querySelectorAll("[data-box-card]"));
            const finishForm = root.querySelector("[data-box-finish]");

            function setState(card, state) {
                card.dataset.state = state;
                STATES.forEach((name) => card.classList.toggle(`box-card-${name}`, name === state));
            }

            // The entrance animation keeps a card at opacity 0 until it runs: a state animation replacing it
            // (opening, answering) would hide the card, and dropping one would replay the entrance.
            function settle(card) {
                card.classList.remove("reveal-ready");
            }

            // After an answer the keyboard goes on to the next closed box, or to a box opened but not answered yet.
            function nextBoxControl(card) {
                const after = cards.slice(cards.indexOf(card) + 1).concat(cards.slice(0, cards.indexOf(card)));
                const closed = after.find((candidate) => candidate.dataset.state === "unopened");
                if (closed) {
                    return closed.querySelector("[data-box-open-form] button");
                }
                const opened = after.find((candidate) => candidate.dataset.state === "opened");
                return opened?.querySelector("[data-answer-form] button:not([disabled])") || null;
            }

            function focusIfStillHere(card, target) {
                const active = document.activeElement;
                if (target && (!active || active === document.body || card.contains(active))) {
                    target.focus({ preventScroll: true });
                    target.closest("[data-box-card]")?.scrollIntoView({
                        block: "nearest",
                        behavior: reducedMotion?.matches ? "auto" : "smooth",
                    });
                }
            }

            async function openBox(card, form) {
                const cover = card.querySelector("[data-box-cover]");
                const panel = card.querySelector("[data-box-question-panel]");
                if (!cover || !panel || card.dataset.state !== "unopened" || card.dataset.opening === "1") {
                    return;
                }
                card.dataset.opening = "1";
                settle(card);
                card.classList.add("box-card-opening");

                // The teacher's preview saves nothing: its boxes open in the page only.
                const [saved] = await Promise.all([
                    preview ? Promise.resolve(true) : submitAction(form, { root }),
                    wait(OPEN_ANIMATION_MS),
                ]);
                card.classList.remove("box-card-opening");
                delete card.dataset.opening;
                if (!saved) {
                    // The error is shown under the button (or the page is already leaving); the box stays closed.
                    return;
                }

                setState(card, "opened");
                cover.hidden = true;
                panel.hidden = false;
                focusFirst(panel);
            }

            async function answerBox(card, form, chosen) {
                if (card.dataset.state === "answered") {
                    return;
                }
                const payload = await submitAction(form, { root, answer: chosen.value });
                if (!payload?.feedback) {
                    return;
                }

                settle(card);
                setState(card, "answered");
                card.classList.add("box-card-answering");
                window.setTimeout(() => card.classList.remove("box-card-answering"), 320);
                const delay = applyChoiceFeedback(
                    Array.from(form.querySelectorAll("button[name='answer']")),
                    // A repeated answer gets the saved one back: only that one is marked.
                    payload.already_answered ? null : chosen,
                    payload.feedback,
                    form.querySelector("[data-question-feedback]"),
                );
                // Finishing early becomes possible after the first answer (the preview has no finish form).
                if (finishForm) {
                    finishForm.hidden = false;
                }

                if (finishIfComplete(payload, root, delay)) {
                    return;
                }
                await wait(delay);
                focusIfStillHere(card, nextBoxControl(card));
            }

            cards.forEach((card) => {
                const openForm = card.querySelector("[data-box-open-form]");
                const answerForm = card.querySelector("[data-answer-form]");

                openForm?.addEventListener("submit", (event) => {
                    event.preventDefault();
                    openBox(card, openForm);
                });

                answerForm?.addEventListener("submit", (event) => {
                    const chosen = event.submitter;
                    if (!chosen || chosen.name !== "answer") {
                        return;
                    }
                    event.preventDefault();
                    answerBox(card, answerForm, chosen);
                });
            });
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
