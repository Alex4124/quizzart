(() => {
    function updateSelectState(select) {
        const card = select.closest(".question-card");
        if (!card) {
            return;
        }
        card.classList.toggle("card-selected", Boolean(select.value));
    }

    function initSelects() {
        document.querySelectorAll("select").forEach((select) => {
            updateSelectState(select);
            select.addEventListener("change", () => updateSelectState(select));
        });
    }

    function fallbackCopyText(text) {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.setAttribute("readonly", "readonly");
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        textarea.style.pointerEvents = "none";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        const success = document.execCommand("copy");
        textarea.remove();
        return success;
    }

    async function copyTextToClipboard(text) {
        if (navigator.clipboard?.writeText) {
            await navigator.clipboard.writeText(text);
            return;
        }

        if (!fallbackCopyText(text)) {
            throw new Error("copy_failed");
        }
    }

    function initCopyLinkButtons() {
        const copyButtons = document.querySelectorAll("[data-copy-link]");
        const toast = document.querySelector("[data-copy-toast]");
        if (!copyButtons.length) {
            return;
        }

        let hideToastTimeoutId = 0;

        function showToast(message, isError = false) {
            if (!toast) {
                return;
            }

            window.clearTimeout(hideToastTimeoutId);
            toast.textContent = message;
            toast.hidden = false;
            toast.classList.add("is-visible");
            toast.classList.toggle("is-error", isError);

            hideToastTimeoutId = window.setTimeout(() => {
                toast.classList.remove("is-visible");
                window.setTimeout(() => {
                    toast.hidden = true;
                    toast.classList.remove("is-error");
                }, 180);
            }, 2200);
        }

        copyButtons.forEach((button) => {
            button.addEventListener("click", async () => {
                const link = button.dataset.copyLink;
                if (!link) {
                    return;
                }

                try {
                    await copyTextToClipboard(link);
                    showToast("\u0421\u0441\u044b\u043b\u043a\u0430 \u0441\u043a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u043d\u0430");
                } catch (error) {
                    showToast("\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0441\u043a\u043e\u043f\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0441\u0441\u044b\u043b\u043a\u0443", true);
                }
            });
        });
    }

    function initSubmitOnceForms() {
        const forms = document.querySelectorAll("form[data-submit-once]");

        function submitButtons(form) {
            const inside = Array.from(form.querySelectorAll("button[type='submit'], button:not([type])"));
            const outside = form.id ? Array.from(document.querySelectorAll(`button[form="${CSS.escape(form.id)}"]`)) : [];
            return inside.concat(outside);
        }

        forms.forEach((form) => {
            form.addEventListener("submit", (event) => {
                // An inline confirm() the teacher cancelled must not lock the form.
                if (event.defaultPrevented) {
                    return;
                }
                if (form.dataset.submitLocked === "1") {
                    event.preventDefault();
                    return;
                }
                form.dataset.submitLocked = "1";
                // Disabling synchronously would drop the clicked button's name/value from the request.
                window.setTimeout(() => {
                    submitButtons(form).forEach((button) => {
                        button.disabled = true;
                    });
                }, 0);
            });
        });

        // A page restored from the back/forward cache must be usable again.
        window.addEventListener("pageshow", (event) => {
            if (!event.persisted) {
                return;
            }
            forms.forEach((form) => {
                delete form.dataset.submitLocked;
                submitButtons(form).forEach((button) => {
                    button.disabled = false;
                });
            });
        });
    }

    // One broken widget must not stop the rest of the page from initialising.
    [
        initSelects,
        initSubmitOnceForms,
        initCopyLinkButtons,
    ].forEach((init) => {
        try {
            init();
        } catch (error) {
            console.error(`[quizzart] ${init.name} failed`, error);
        }
    });
})();
