document.addEventListener("DOMContentLoaded", () => {
  const dialog = document.querySelector("#quick-interaction-dialog");
  const contactSelect = dialog?.querySelector("[name=contact]");
  const jobSelect = dialog?.querySelector("[data-dependent-job]");

  document.querySelectorAll("[data-open-interaction]").forEach((button) => {
    button.addEventListener("click", () => {
      if (!dialog) return;
      if (button.dataset.contactId) {
        contactSelect.value = button.dataset.contactId;
        contactSelect.dispatchEvent(new Event("change"));
      }
      dialog.showModal();
    });
  });

  dialog?.querySelectorAll("[data-close-interaction]").forEach((button) => {
    button.addEventListener("click", () => dialog.close());
  });

  const filterJobs = () => {
    if (!contactSelect || !jobSelect) return;
    for (const option of jobSelect.options) {
      if (!option.value) continue;
      const contactIds = (option.dataset.contactIds || "").split(",");
      option.hidden = !contactIds.includes(contactSelect.value);
      if (option.hidden && option.selected) jobSelect.value = "";
    }
  };
  contactSelect?.addEventListener("change", filterJobs);
  filterJobs();

  let draggedCard = null;
  document.querySelectorAll("[data-job-card]").forEach((card) => {
    card.addEventListener("dragstart", (event) => {
      draggedCard = card;
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", card.dataset.jobId);
      card.classList.add("dragging");
    });
    card.addEventListener("dragend", () => {
      card.classList.remove("dragging");
      draggedCard = null;
    });
  });
  document.querySelectorAll("[data-status-column]").forEach((column) => {
    column.addEventListener("dragover", (event) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      column.classList.add("drop-target");
    });
    column.addEventListener("dragleave", () => {
      column.classList.remove("drop-target");
    });
    column.addEventListener("drop", (event) => {
      event.preventDefault();
      column.classList.remove("drop-target");
      if (!draggedCard || draggedCard.closest("[data-status-column]") === column) {
        return;
      }
      const select = draggedCard.querySelector("[name=status]");
      const form = draggedCard.querySelector("[data-status-form]");
      if (select && form) {
        select.value = column.dataset.statusColumn;
        form.requestSubmit();
      }
    });
  });
});
