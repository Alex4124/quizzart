(() => {
    // Field names the unsaved-changes check ignores: the token, the remembered tab and the per-card radio groups
    // of question-bank-editor.js (their state already lives in items_json).
    const UNTRACKED_FIELDS = new Set(["csrfmiddlewaretoken", "active_tab"]);
    const UNTRACKED_PREFIX = "qb-correct-";
    const LEAVE_MESSAGE = "Есть несохранённые изменения. Уйти со страницы без сохранения?";
    const PREVIEW_WIDTH = 1280;
    // Long enough for the entrance animations of the players; after that the thumbnail stands still.
    const PREVIEW_FREEZE_DELAY_MS = 1500;

    function initEditorTabs() {
        const root = document.querySelector("[data-editor-shell]");
        if (!root) {
            return null;
        }

        const hiddenInput = root.querySelector("[data-editor-active-tab]");
        const tabList = root.querySelector("[data-editor-tablist]");
        const triggers = Array.from(root.querySelectorAll("[data-editor-tab-trigger]"));
        const panels = Array.from(root.querySelectorAll("[data-editor-panel]"));

        // In the folded (row) layout the tabs scroll sideways: keep the current one in sight, without moving the page.
        function revealTab(trigger) {
            if (!tabList || tabList.scrollWidth <= tabList.clientWidth) {
                return;
            }
            const listRect = tabList.getBoundingClientRect();
            const rect = trigger.getBoundingClientRect();
            if (rect.left < listRect.left) {
                tabList.scrollLeft -= listRect.left - rect.left + 8;
            } else if (rect.right > listRect.right) {
                tabList.scrollLeft += rect.right - listRect.right + 8;
            }
        }

        function setActiveTab(tabKey, updateUrl = true) {
            if (!tabKey) {
                return;
            }

            triggers.forEach((trigger) => {
                const isActive = trigger.dataset.editorTabTrigger === tabKey;
                trigger.classList.toggle("is-active", isActive);
                trigger.setAttribute("aria-selected", String(isActive));
                // Roving tabindex: Tab reaches the current tab, arrows move between tabs.
                trigger.tabIndex = isActive ? 0 : -1;
                if (isActive) {
                    revealTab(trigger);
                }
            });

            panels.forEach((panel) => {
                panel.classList.toggle("is-active", panel.dataset.editorPanel === tabKey);
            });

            root.dataset.activeTab = tabKey;
            if (hiddenInput) {
                hiddenInput.value = tabKey;
            }

            if (updateUrl) {
                const url = new URL(window.location.href);
                url.searchParams.set("tab", tabKey);
                url.hash = "editor-workspace";
                window.history.replaceState({}, "", url);
            }
        }

        triggers.forEach((trigger, index) => {
            trigger.addEventListener("click", (event) => {
                event.preventDefault();
                setActiveTab(trigger.dataset.editorTabTrigger);
            });

            trigger.addEventListener("keydown", (event) => {
                const steps = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 };
                let nextIndex = null;
                if (event.key in steps) {
                    nextIndex = (index + steps[event.key] + triggers.length) % triggers.length;
                } else if (event.key === "Home") {
                    nextIndex = 0;
                } else if (event.key === "End") {
                    nextIndex = triggers.length - 1;
                } else if (event.key === " ") {
                    // A link ignores Space; a tab should not scroll the page instead.
                    event.preventDefault();
                    setActiveTab(trigger.dataset.editorTabTrigger);
                    return;
                }
                if (nextIndex === null) {
                    return;
                }
                event.preventDefault();
                const next = triggers[nextIndex];
                setActiveTab(next.dataset.editorTabTrigger);
                next.focus();
            });
        });

        // The tabs stand in a column in the sidebar and in a row once the sidebar folds (editor.css, 1120px).
        if (tabList && window.matchMedia) {
            const rowLayout = window.matchMedia("(max-width: 1120px)");
            const syncOrientation = () => {
                tabList.setAttribute("aria-orientation", rowLayout.matches ? "horizontal" : "vertical");
            };
            syncOrientation();
            rowLayout.addEventListener?.("change", syncOrientation);
        }

        const hashTarget = window.location.hash.replace(/^#tab-/, "");
        if (hashTarget && panels.some((panel) => panel.dataset.editorPanel === hashTarget)) {
            setActiveTab(hashTarget, false);
        } else {
            setActiveTab(root.dataset.activeTab || "general", false);
        }

        return {
            setActiveTab,
        };
    }

    function initTemplateCards(tabApi) {
        const select = document.querySelector("[data-template-switch]");
        const cards = Array.from(document.querySelectorAll("[data-template-card]"));
        if (!select || !cards.length) {
            return;
        }

        function syncSelectedCard(selectedKey) {
            cards.forEach((card) => {
                const isSelected = card.dataset.templateKey === selectedKey;
                card.classList.toggle("is-selected", isSelected);
                card.setAttribute("aria-pressed", String(isSelected));
            });
        }

        syncSelectedCard(select.value);
        select.addEventListener("change", () => {
            syncSelectedCard(select.value);
        });

        cards.forEach((card) => {
            card.addEventListener("click", () => {
                const nextKey = card.dataset.templateKey || "";
                if (!nextKey || nextKey === select.value) {
                    if (tabApi) {
                        tabApi.setActiveTab("general");
                    }
                    return;
                }

                if (tabApi) {
                    tabApi.setActiveTab(card.dataset.editorTargetTab || "general");
                }

                syncSelectedCard(nextKey);
                select.value = nextKey;
                select.dispatchEvent(new Event("change", { bubbles: true }));
            });
        });
    }

    // Warns before the teacher leaves with unsaved changes: the browser's own prompt on reload/close,
    // a confirm() on links that leave the editor. Saving (any form submit) never asks.
    function initUnsavedChangesGuard() {
        const form = document.querySelector("[data-activity-editor-form]");
        if (!form) {
            return;
        }

        function snapshot() {
            const entries = [];
            new FormData(form).forEach((value, key) => {
                if (UNTRACKED_FIELDS.has(key) || key.startsWith(UNTRACKED_PREFIX)) {
                    return;
                }
                entries.push([key, typeof value === "string" ? value : value.name]);
            });
            return JSON.stringify(entries);
        }

        // Taken after question-bank-editor.js has built the cards and written items_json.
        const initialState = snapshot();
        // A page that came back from a POST (errors, template switch) is not saved yet.
        const startsUnsaved = form.hasAttribute("data-unsaved-post");
        let leaving = false;

        function hasUnsavedChanges() {
            return !leaving && (startsUnsaved || snapshot() !== initialState);
        }

        // Bubbling to the document runs after the forms' own handlers: a cancelled confirm() or the
        // submit-once lock has already called preventDefault() and the page stays.
        document.addEventListener("submit", (event) => {
            if (!event.defaultPrevented) {
                leaving = true;
            }
        });

        // «Дублировать» copies the saved version: say that the changes on this page would be lost.
        document.querySelectorAll("[data-confirm-unsaved]").forEach((button) => {
            button.addEventListener("click", (event) => {
                if (hasUnsavedChanges() && !window.confirm(button.dataset.confirmUnsaved || LEAVE_MESSAGE)) {
                    event.preventDefault();
                }
            });
        });

        document.addEventListener("click", (event) => {
            if (
                event.defaultPrevented ||
                event.button !== 0 ||
                event.metaKey ||
                event.ctrlKey ||
                event.shiftKey ||
                event.altKey
            ) {
                return;
            }
            const link = event.target.closest("a[href]");
            // New tabs (preview, share link) and the editor's own tabs keep this page open.
            if (!link || link.target === "_blank" || link.hasAttribute("download") || link.matches("[data-editor-tab-trigger]")) {
                return;
            }
            const url = new URL(link.href, window.location.href);
            const here = new URL(window.location.href);
            if (url.origin === here.origin && url.pathname === here.pathname && url.search === here.search && url.hash) {
                return;
            }
            if (!hasUnsavedChanges()) {
                return;
            }
            if (window.confirm(LEAVE_MESSAGE)) {
                leaving = true;
            } else {
                event.preventDefault();
            }
        });

        window.addEventListener("beforeunload", (event) => {
            if (!hasUnsavedChanges()) {
                return;
            }
            event.preventDefault();
            // Older browsers still need returnValue for the prompt; the text itself is never shown.
            event.returnValue = "";
        });

        // Back from the bfcache: the page is still open, the guard must work again.
        window.addEventListener("pageshow", (event) => {
            if (event.persisted) {
                leaving = false;
            }
        });
    }

    // The side preview: the real preview at a desktop width, scaled down to the column. It loads once the card
    // is on screen and then stands still (CSS animations paused, animation-frame loops stopped), so the snake
    // and the wheel lights do not keep the CPU busy while the teacher edits.
    function initPreviewThumbnail() {
        const frame = document.querySelector("[data-preview-thumb]");
        const iframe = frame?.querySelector("iframe[data-src]");
        if (!frame || !iframe) {
            return;
        }

        function updateScale() {
            const width = frame.clientWidth;
            if (width) {
                frame.style.setProperty("--preview-scale", String(width / PREVIEW_WIDTH));
            }
        }

        function freeze() {
            try {
                const previewWindow = iframe.contentWindow;
                const previewDocument = iframe.contentDocument;
                if (!previewWindow || !previewDocument?.head) {
                    return;
                }
                const style = previewDocument.createElement("style");
                style.textContent =
                    "*, *::before, *::after { animation-play-state: paused !important; transition: none !important; }";
                previewDocument.head.appendChild(style);
                previewWindow.requestAnimationFrame = () => 0;
            } catch (error) {
                // A preview from another origin cannot be reached; it simply keeps running.
            }
        }

        function load() {
            iframe.addEventListener("load", () => window.setTimeout(freeze, PREVIEW_FREEZE_DELAY_MS), { once: true });
            iframe.src = iframe.dataset.src;
            iframe.removeAttribute("data-src");
        }

        updateScale();
        if ("ResizeObserver" in window) {
            new ResizeObserver(updateScale).observe(frame);
        } else {
            window.addEventListener("resize", updateScale);
        }

        if ("IntersectionObserver" in window) {
            const observer = new IntersectionObserver((entries) => {
                if (entries.some((entry) => entry.isIntersecting)) {
                    observer.disconnect();
                    load();
                }
            });
            observer.observe(frame);
        } else {
            load();
        }
    }

    // One broken widget must not stop the rest of the page from initialising.
    function safely(init, ...args) {
        try {
            return init(...args);
        } catch (error) {
            console.error(`[quizzart] ${init.name} failed`, error);
            return null;
        }
    }

    const tabApi = safely(initEditorTabs);
    safely(initTemplateCards, tabApi);
    safely(initUnsavedChangesGuard);
    safely(initPreviewThumbnail);
})();
