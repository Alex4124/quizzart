(() => {
    const { wait, submitAction, applyChoiceFeedback, finishIfComplete, focusFirst, isPreview, previewAnsweredKeys } =
        window.QuizzartPlayer;
    const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)");

    // The pointer sits on the left of the wheel, which is the 180deg stopping angle.
    const POINTER_ANGLE = 180;
    // Degrees per millisecond while the wheel spins freely (2.5 turns a second).
    const FREE_SPIN_SPEED = 0.9;
    const LANDING_DURATION = 1800;
    const QUESTION_EXIT_DELAY = 260;
    const REPEAT_NOTICE = "Этот вопрос уже был — крутите ещё раз.";

    // Spotlight title and text for each state. Same wording as the play page renders without JavaScript.
    const SPOTLIGHT = {
        idle: [
            "Крутите колесо, чтобы получить вопрос",
            "Каждый сектор открывает отдельный вопрос и сохраняет результат после ответа.",
        ],
        spinning: ["Колесо крутится", "Нажмите «Остановить», и колесо выберет вопрос."],
        landing: ["Колесо выбирает вопрос", "Ещё мгновение — и вопрос откроется."],
        question: ["Колесо выбрало вопрос", "Выберите один вариант ответа: изменить его потом не получится."],
        repeat: ["Этот вопрос уже был", "Ниже — ваш прошлый ответ. Крутите колесо ещё раз."],
        done: ["Все вопросы пройдены", "На каждый сектор уже есть ответ."],
    };

    function initWheelPlayers() {
        document.querySelectorAll("[data-wheel-player]").forEach((root) => {
            const disc = root.querySelector("[data-wheel-disc]");
            const spinForm = root.querySelector("[data-wheel-spin-form]");
            const startButton = root.querySelector("[data-wheel-start]");
            const stopButton = root.querySelector("[data-wheel-stop]");
            const notice = root.querySelector("[data-wheel-notice]");
            const finishForm = root.querySelector("[data-wheel-finish]");
            const questionStack = root.querySelector(".wheel-question-stack");
            const spotlightTitle = root.querySelector("[data-wheel-spotlight-title]");
            const spotlightText = root.querySelector("[data-wheel-spotlight-text]");
            const sectors = Array.from(root.querySelectorAll("[data-wheel-sector]"));
            const questions = new Map(
                Array.from(root.querySelectorAll("[data-wheel-question]")).map((card) => [card.dataset.itemId || "", card]),
            );

            if (!disc || !spinForm || !startButton || !stopButton || !sectors.length) {
                return;
            }

            const preview = isPreview(root);
            // idle | spinning | landing | question
            let state = "idle";
            let rotation = 0;
            let freeSpinFrame = 0;
            let activeItemId = "";
            // The card on screen: the open question, or an answered one the wheel stopped on again.
            let shownCard = null;
            // The server's reply to the current spin; it is usually there before «Остановить» is pressed.
            let spinReply = null;
            let questionStackMinHeight = 0;

            function sectorOf(itemId) {
                return sectors.find((sector) => sector.dataset.itemId === itemId) || null;
            }

            function hasUnanswered() {
                return sectors.some((sector) => sector.dataset.answered !== "1");
            }

            function updateQuestionStackHeight() {
                if (!questionStack) {
                    return;
                }
                // The sidebar never shrinks back, so the page does not jump when a card closes.
                window.requestAnimationFrame(() => {
                    questionStackMinHeight = Math.max(questionStackMinHeight, questionStack.getBoundingClientRect().height);
                    if (questionStackMinHeight > 0) {
                        questionStack.style.minHeight = `${Math.ceil(questionStackMinHeight)}px`;
                    }
                });
            }

            function setState(next, spotlight = next) {
                state = next;
                root.dataset.wheelState = next;
                startButton.disabled = next !== "idle" || !hasUnanswered();
                stopButton.disabled = next !== "spinning";
                const [title, text] = SPOTLIGHT[spotlight] || SPOTLIGHT.idle;
                if (spotlightTitle) {
                    spotlightTitle.textContent = title;
                }
                if (spotlightText) {
                    spotlightText.textContent = text;
                }
                updateQuestionStackHeight();
            }

            function showNotice(message, { error = false } = {}) {
                if (!notice) {
                    return;
                }
                notice.classList.toggle("is-error", error);
                notice.textContent = message;
                notice.hidden = !message;
            }

            function markActive(itemId) {
                sectors.forEach((sector) => sector.classList.toggle("wheel-sector-active", sector.dataset.itemId === itemId));
            }

            function markAnswered(itemId) {
                const sector = sectorOf(itemId);
                if (sector) {
                    sector.dataset.answered = "1";
                    sector.classList.add("wheel-sector-answered");
                    sector.classList.remove("wheel-sector-active");
                }
            }

            // Scrolls as little as needed to show the element (on a phone the question opens under the wheel),
            // clear of the sticky top bar. alignEnd keeps the element at the bottom, with the wheel above it.
            function bringIntoView(element, { alignEnd = false } = {}) {
                if (!element) {
                    return;
                }
                const rect = element.getBoundingClientRect();
                const top = (document.querySelector(".player-topbar")?.getBoundingClientRect().bottom || 0) + 12;
                const bottom = window.innerHeight - 12;
                if (rect.top >= top && rect.bottom <= bottom) {
                    return;
                }
                const fits = rect.height <= bottom - top;
                const delta = alignEnd || (fits && rect.top >= top) ? rect.bottom - bottom : rect.top - top;
                window.scrollBy({ top: delta, behavior: reducedMotion?.matches ? "auto" : "smooth" });
            }

            function showCard(card) {
                questions.forEach((candidate) => {
                    if (candidate !== card) {
                        candidate.hidden = true;
                        candidate.classList.remove("wheel-question-card-enter", "wheel-question-card-exit");
                    }
                });
                shownCard = card;
                card.classList.remove("wheel-question-card-enter", "wheel-question-card-exit");
                card.hidden = false;
                window.requestAnimationFrame(() => card.classList.add("wheel-question-card-enter"));
                updateQuestionStackHeight();
            }

            async function hideShownCard() {
                const card = shownCard;
                shownCard = null;
                if (!card || card.hidden) {
                    return;
                }
                card.classList.remove("wheel-question-card-enter");
                card.classList.add("wheel-question-card-exit");
                await wait(QUESTION_EXIT_DELAY);
                // The wheel may have stopped on this card again in the meantime.
                if (shownCard !== card) {
                    card.hidden = true;
                }
                card.classList.remove("wheel-question-card-exit");
            }

            // ---- The wheel ------------------------------------------------------------------------

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
                    sector.style.setProperty("--wheel-sector-center-angle", `${(-90 + sectorIndex * sectorSizeDegrees).toFixed(3)}deg`);
                    sector.style.setProperty("--wheel-label-rotation", "180deg");
                });
            }

            // The rotation that puts the sector under the pointer after at least `turns` full turns.
            function rotationFor(sector, turns) {
                const sectorSize = 360 / sectors.length;
                const sectorCenterAngle = -90 + sectors.indexOf(sector) * sectorSize;
                const targetAngle = POINTER_ANGLE - sectorCenterAngle;
                const normalizedRotation = ((rotation % 360) + 360) % 360;
                const delta = (((targetAngle - normalizedRotation) % 360) + 360) % 360;
                return rotation + turns * 360 + delta;
            }

            function startFreeSpin() {
                disc.classList.add("wheel-disc-live");
                disc.style.transition = "none";
                let last = performance.now();
                const step = (now) => {
                    rotation += (now - last) * FREE_SPIN_SPEED;
                    last = now;
                    applyRotation(rotation);
                    freeSpinFrame = window.requestAnimationFrame(step);
                };
                freeSpinFrame = window.requestAnimationFrame(step);
            }

            function stopFreeSpin() {
                window.cancelAnimationFrame(freeSpinFrame);
                freeSpinFrame = 0;
                disc.classList.remove("wheel-disc-live");
            }

            function turnTo(sector) {
                stopFreeSpin();
                disc.style.transition = "none";
                rotation = rotationFor(sector, 0);
                applyRotation(rotation);
            }

            async function slowDownOnto(sector) {
                window.cancelAnimationFrame(freeSpinFrame);
                freeSpinFrame = 0;
                if (reducedMotion?.matches) {
                    turnTo(sector);
                    return;
                }
                const target = rotationFor(sector, 2);
                // The curve starts at the free spin's speed, so the wheel does not jerk when it begins to slow down.
                const startSlope = Math.min(3, (FREE_SPIN_SPEED * LANDING_DURATION) / Math.max(target - rotation, 1));
                disc.style.transition = `transform ${LANDING_DURATION}ms cubic-bezier(0.25, ${(0.25 * startSlope).toFixed(3)}, 0.2, 1)`;
                rotation = target;
                applyRotation(rotation);
                await wait(LANDING_DURATION);
                disc.classList.remove("wheel-disc-live");
            }

            // ---- Spinning -------------------------------------------------------------------------

            function backToIdle() {
                stopFreeSpin();
                setState("idle", hasUnanswered() ? "idle" : "done");
                bringIntoView(startButton.closest(".wheel-controls"), { alignEnd: true });
                startButton.focus({ preventScroll: true });
            }

            function openQuestion(itemId, { focus = true } = {}) {
                const card = questions.get(itemId);
                activeItemId = itemId;
                markActive(itemId);
                showNotice("");
                showCard(card);
                setState("question");
                if (focus) {
                    bringIntoView(card);
                    focusFirst(card);
                }
            }

            function showRepeat(spin, card) {
                if (spin.previous) {
                    // The saved answer, in case it was given in another tab.
                    applyChoiceFeedback(
                        Array.from(card.querySelectorAll("button[name='answer']")),
                        null,
                        spin.previous,
                        card.querySelector("[data-question-feedback]"),
                    );
                }
                markActive("");
                showCard(card);
                showNotice(REPEAT_NOTICE);
                setState("idle", "repeat");
                startButton.focus({ preventScroll: true });
            }

            async function land() {
                const payload = await spinReply;
                spinReply = null;
                if (state !== "landing") {
                    return;
                }
                if (!payload) {
                    // The error is already shown under the buttons, or the page is being reloaded.
                    backToIdle();
                    return;
                }
                const spin = payload.spin;
                if (!spin) {
                    stopFreeSpin();
                    finishIfComplete(payload, root);
                    setState("idle", "done");
                    return;
                }
                const sector = sectorOf(spin.item_key);
                const card = questions.get(spin.item_key);
                if (!sector || !card) {
                    showNotice("Вопросы колеса изменились. Обновите страницу.", { error: true });
                    backToIdle();
                    return;
                }
                await slowDownOnto(sector);
                if (spin.repeat) {
                    showRepeat(spin, card);
                    return;
                }
                openQuestion(spin.item_key);
            }

            function startSpin() {
                if (state !== "idle" || !hasUnanswered()) {
                    return;
                }
                showNotice("");
                markActive("");
                hideShownCard();
                // The spin goes to the server at once: its reply is usually back before «Остановить» is pressed.
                spinReply = submitAction(spinForm, {
                    root,
                    fields: preview ? { answered: previewAnsweredKeys(root), active_item: activeItemId } : {},
                });
                if (reducedMotion?.matches) {
                    // No free spinning: the wheel turns straight to the sector once the server has picked it.
                    setState("landing");
                    land();
                    return;
                }
                const reply = spinReply;
                setState("spinning");
                startFreeSpin();
                stopButton.focus({ preventScroll: true });
                reply.then((payload) => {
                    // A failed spin stops the wheel at once instead of waiting for «Остановить».
                    if (!payload && state === "spinning" && spinReply === reply) {
                        spinReply = null;
                        backToIdle();
                    }
                });
            }

            function stopSpin() {
                if (state !== "spinning") {
                    return;
                }
                setState("landing");
                land();
            }

            // ---- Answers ----------------------------------------------------------------------------

            questions.forEach((card, itemId) => {
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
                    if (state !== "question" || activeItemId !== itemId || card.dataset.state === "answered") {
                        return;
                    }

                    const payload = await submitAction(form, { root, answer: chosen.value });
                    if (!payload?.feedback) {
                        return;
                    }

                    card.dataset.state = "answered";
                    activeItemId = "";
                    markAnswered(itemId);
                    if (finishForm) {
                        finishForm.hidden = false;
                    }
                    const delay = applyChoiceFeedback(options, chosen, payload.feedback, form.querySelector("[data-question-feedback]"));
                    bringIntoView(card);
                    if (finishIfComplete(payload, root, delay)) {
                        setState("idle", "done");
                        return;
                    }
                    await wait(delay);
                    await hideShownCard();
                    backToIdle();
                });
            });

            spinForm.addEventListener("submit", (event) => {
                event.preventDefault();
                startSpin();
            });
            stopButton.addEventListener("click", stopSpin);
            layoutWheelLabels();
            window.addEventListener("resize", layoutWheelLabels);

            // A question the wheel stopped on before a reload stays open: the server sent it with the page.
            const resumedId = root.dataset.activeItem || "";
            const resumedSector = sectorOf(resumedId);
            if (resumedSector && questions.has(resumedId) && resumedSector.dataset.answered !== "1") {
                turnTo(resumedSector);
                openQuestion(resumedId, { focus: false });
            } else {
                questions.forEach((card) => {
                    card.hidden = true;
                });
                setState("idle", hasUnanswered() ? "idle" : "done");
            }
        });
    }

    // One broken widget must not stop the rest of the page from initialising.
    [
        initWheelPlayers,
    ].forEach((init) => {
        try {
            init();
        } catch (error) {
            console.error(`[quizzart] ${init.name} failed`, error);
        }
    });
})();
