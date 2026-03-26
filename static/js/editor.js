(() => {
    function initEditorTabs() {
        const root = document.querySelector("[data-editor-shell]");
        if (!root) {
            return null;
        }

        const hiddenInput = root.querySelector("[data-editor-active-tab]");
        const triggers = Array.from(root.querySelectorAll("[data-editor-tab-trigger]"));
        const panels = Array.from(root.querySelectorAll("[data-editor-panel]"));

        function setActiveTab(tabKey, updateUrl = true) {
            if (!tabKey) {
                return;
            }

            triggers.forEach((trigger) => {
                trigger.classList.toggle("is-active", trigger.dataset.editorTabTrigger === tabKey);
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

        triggers.forEach((trigger) => {
            trigger.addEventListener("click", (event) => {
                event.preventDefault();
                setActiveTab(trigger.dataset.editorTabTrigger);
            });
        });

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
                card.classList.toggle("is-selected", card.dataset.templateKey === selectedKey);
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

    const tabApi = initEditorTabs();
    initTemplateCards(tabApi);
})();
