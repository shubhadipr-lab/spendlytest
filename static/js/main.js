// main.js — students will add JavaScript here as features are built

document.addEventListener("submit", function (event) {
    const form = event.target;
    if (form.classList.contains("delete-expense-form")) {
        const confirmed = confirm("Delete this expense? This cannot be undone.");
        if (!confirmed) {
            event.preventDefault();
        }
    }
});
