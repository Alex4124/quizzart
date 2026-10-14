(() => {
    const { nativeSubmit, markSelectedOption, preserveSubmittedValue, revealChoiceState, enhanceAnswerForm, submitFormAsJson } = window.QuizzartPlayer;

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
