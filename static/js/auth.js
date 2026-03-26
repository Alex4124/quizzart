(() => {
    document.querySelectorAll("[data-password-toggle]").forEach((button) => {
        const inputId = button.dataset.target || "";
        const input = inputId ? document.getElementById(inputId) : null;
        if (!input) {
            return;
        }

        const showLabel = button.dataset.showLabel || "Показать пароль";
        const hideLabel = button.dataset.hideLabel || "Скрыть пароль";

        button.addEventListener("click", () => {
            const nextVisible = input.type === "password";
            input.type = nextVisible ? "text" : "password";
            button.classList.toggle("is-visible", nextVisible);
            button.setAttribute("aria-pressed", String(nextVisible));
            button.setAttribute("aria-label", nextVisible ? hideLabel : showLabel);
        });
    });
})();
