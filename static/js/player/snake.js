(() => {
    const { wait, submitAction, applyChoiceFeedback, finishIfComplete, focusFirst, isPreview } = window.QuizzartPlayer;

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
            const preview = isPreview(root);
            const board = root.querySelector("[data-snake-board]");
            const playfield = root.querySelector("[data-snake-playfield]");
            const head = root.querySelector("[data-snake-head]");
            const segmentHost = root.querySelector("[data-snake-segments]");
            const questionLayer = root.querySelector("[data-snake-question-layer]");
            const finishCard = root.querySelector(preview ? "[data-preview-complete]" : "[data-snake-finish]");
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

            let frameId = null;
            let boardRect = null;
            let paused = false;
            let completed = false;
            // Apples answered before a reload are rendered eaten: the snake keeps the length it had.
            let answeredCount = appleElements.filter((apple) => apple.dataset.eaten === "1").length;
            let activeItemId = "";
            let lastTimestamp = 0;
            let headPoint = { x: 0, y: 0 };
            let heading = { x: 1, y: 0 };
            let queuedHeading = null;
            const bodyPoints = [];
            const segments = [];
            const baseSegmentCount = 5;
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
                    // Each new segment goes one step behind the tail. Stacking several on the tail point (a reload
                    // with saved answers adds them all at once) folded the chain back over itself.
                    const anchorPoint = !bodyPoints.length
                        ? {
                            x: headPoint.x - heading.x * headSegmentDistance,
                            y: headPoint.y - heading.y * headSegmentDistance,
                        }
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

            // The HUD shows what the server counted, so a reload and a second tab agree with it.
            function updateHud(payload) {
                const total = Number(payload.total_count) || appleElements.length;
                const answered = Math.min(Number(payload.answered_count) || 0, total);
                if (progressValue) {
                    progressValue.textContent = String(answered);
                }
                if (remainingValue) {
                    remainingValue.textContent = String(Math.max(total - answered, 0));
                }
                if (scoreValue && "score" in payload) {
                    scoreValue.textContent = payload.score === null ? "—" : String(payload.score);
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
                updateDirectionControls();
            }

            function eatApple(itemId) {
                const apple = appleMap.get(itemId);
                if (!apple || apple.dataset.eaten === "1") {
                    return;
                }
                apple.dataset.eaten = "1";
                apple.classList.remove("snake-apple-bite");
                apple.classList.add("snake-apple-eaten");
                answeredCount += 1;
                syncSegments();
            }

            function finishRun(payload) {
                completed = true;
                paused = true;
                activeItemId = "";
                root.classList.add("snake-player-paused");
                questionLayer.hidden = false;
                questionCards.forEach((card) => {
                    card.hidden = true;
                    card.classList.remove("snake-question-card-live");
                });
                if (finishCard) {
                    finishCard.hidden = false;
                    finishCard.classList.add("snake-question-card-live");
                    finishCard.focus({ preventScroll: true });
                }
                updateDirectionControls();
                // Students go to their results, the teacher's preview keeps the note on the board.
                finishIfComplete(payload, root, 360);
            }

            function showQuestion(itemId) {
                const card = questionMap.get(itemId);
                if (!card || card.dataset.state === "answered") {
                    paused = false;
                    root.classList.remove("snake-player-paused");
                    updateDirectionControls();
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
                updateDirectionControls();
                focusFirst(card);
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

            async function answerQuestion(card, form, options, chosen) {
                const itemId = card.dataset.itemId || "";
                const payload = await submitAction(form, { root, answer: chosen.value });
                if (!payload?.feedback) {
                    // The card stays open: an error is shown in it, or the page is already posting without fetch.
                    return;
                }

                card.dataset.state = "answered";
                updateHud(payload);
                const delay = applyChoiceFeedback(options, chosen, payload.feedback, form.querySelector("[data-question-feedback]"));
                await wait(delay);
                eatApple(itemId);

                if (payload.is_complete) {
                    finishRun(payload);
                    return;
                }
                hideQuestionLayer();
                if (!appleElements.some((apple) => apple.dataset.eaten !== "1")) {
                    // The activity gained a question after this page was opened: the server shows the rest.
                    window.location.reload();
                    return;
                }
                playfield.focus({ preventScroll: true });
            }

            function handleDirectionKeydown(event) {
                const directionName = directionKeys[event.key];
                if (!directionName || event.altKey || event.ctrlKey || event.metaKey) {
                    return;
                }
                // While a question is open the arrows belong to the page, not to the snake.
                if (paused || completed) {
                    return;
                }

                const target = event.target;
                if (
                    target instanceof HTMLElement &&
                    target.closest("input, textarea, select, button, [contenteditable='true']") &&
                    !target.closest("[data-snake-direction]")
                ) {
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

                // The run is over: one last frame settles the body, then the loop stops burning CPU.
                if (completed) {
                    frameId = null;
                    return;
                }
                frameId = window.requestAnimationFrame(tick);
            }

            questionCards.forEach((card) => {
                const form = card.querySelector("[data-answer-form]");
                if (!form) {
                    return;
                }
                const options = Array.from(form.querySelectorAll("button[name='answer']"));

                form.addEventListener("submit", (event) => {
                    const chosen = event.submitter;
                    if (!chosen || chosen.name !== "answer") {
                        return;
                    }
                    event.preventDefault();
                    if (completed || card.dataset.state === "answered" || card.dataset.itemId !== activeItemId) {
                        return;
                    }
                    answerQuestion(card, form, options, chosen);
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
            updateDirectionControls();
            renderSnake();
            frameId = window.requestAnimationFrame(tick);
        });
    }

    // One broken widget must not stop the rest of the page from initialising.
    [
        initSnakePlayers,
    ].forEach((init) => {
        try {
            init();
        } catch (error) {
            console.error(`[quizzart] ${init.name} failed`, error);
        }
    });
})();
